# 5. Data: persistence, backup, restore

Votes are the only state worth keeping. Redis holds the queue (AOF on a disk), PostgreSQL holds the votes (disk), backups go to Azure Blob.

The proof of every test here is the **result page**: before breaking anything, **take a screenshot** of it (total and the four percentages). After recovery, the page must match the screenshot exactly. Stop the zero-downtime checker if it still runs: its votes would change the numbers.

## data-1: votes survive a database restart

1. Screenshot the result page.
2. Terminal A:
   ```sh
   kubectl -n $NS delete pod postgres-0 redis-0
   kubectl -n $NS wait --for=condition=Ready pod/postgres-0 pod/redis-0 --timeout=5m
   ```
3. Watch the result page during the restart; when both pods are Ready, reload it once.
4. Terminal A: `kubectl -n $NS get pvc`.

**Expect:** during the restart the result page freezes or goes white; afterwards it shows **exactly the screenshot's numbers**. The PVCs are the same ones as before (same names, AGE counted in hours, not seconds): the pods came back on the same disks.

## data-2: votes survive an uninstall and a reinstall

**Why:** `Retain` policy: losing the votes must always be a deliberate step. The PVCs outlive `helm uninstall`.

1. Screenshot the result page.
2. Terminal A:
   ```sh
   make destroy                                   # without DELETE_PVC
   kubectl -n $NS get pvc
   ```
3. Reload poll and result in the browser.
4. Terminal A: `make deploy`. Then reload both pages.

**Expect:**
- step 2: only the two PVCs remain (`data-postgres-0`, `data-redis-0`), and the script says they are still billed;
- step 3: both pages are gone (Traefik's `404 page not found`): the application is uninstalled;
- step 4: both pages are back, and the result page shows **exactly the screenshot**. A new vote adds to the old total. The URL is the same (the Traefik IP did not change).

Mind the PostgreSQL password trap (deploy-10): use the **same** `POSTGRES_PASSWORD` as the first install, because the data directory keeps the first one.

**Cost note to record:** while uninstalled, the two disks keep billing ([cost.md](../cost.md)).

## data-3: the backup CronJob runs and uploads (first real run on AKS)

**Why:** `data-3` and `data-4` are the first run of the backup path on a real cluster ([restore.md](../runbooks/restore.md#tested) says upload and download are untested).

**Prerequisites:** the backup resources exist (`terraform apply` done from `infra/terraform`; this creates a storage account: check [cost.md](../cost.md) first). Backup is **off by default**; `make deploy` enables it when the three `BACKUP_*` variables are set ([deploy.md](../deploy.md#use)).

```sh
export BACKUP_STORAGE_ACCOUNT=$(terraform -chdir=infra/terraform output -raw backup_storage_account)
export BACKUP_CONTAINER=$(terraform -chdir=infra/terraform output -raw backup_container)
export BACKUP_CLIENT_ID=$(terraform -chdir=infra/terraform output -raw backup_client_id)
ACCOUNT=$BACKUP_STORAGE_ACCOUNT CONTAINER=$BACKUP_CONTAINER
IMAGE_TAG=$(helm -n $NS get values bernstein -a -o json | jq -r .global.tag) make deploy
kubectl -n $NS get cronjob postgres-backup
kubectl -n $NS create job backup-manual --from=cronjob/postgres-backup
kubectl -n $NS wait --for=condition=complete job/backup-manual --timeout=5m
kubectl -n $NS logs job/backup-manual --all-containers
az storage blob list --auth-mode login --account-name $ACCOUNT -c $CONTAINER --query '[].{name:name,size:properties.contentLength}' -o table
```

`IMAGE_TAG` from the running release keeps the same images, so nothing is rebuilt and only the backup objects are added (`POSTGRES_PASSWORD` and the cluster variables are still exported from [02-deploy.md](02-deploy.md)). Then run `make deploy` a **second** time with the same variables and check `kubectl -n $NS get cronjob postgres-backup` still answers: the backup survives a redeploy.

**Expect:**
- the CronJob exists with schedule `0 */6 * * *`;
- the Job completes; logs show the `dump` init container producing a file and the `upload` container uploading a blob without error, no mention of a storage key (workload identity);
- `az storage blob list` shows one blob named like `20261014T120000Z.pgdump`, size greater than a few hundred bytes.

Your user needs `Storage Blob Data Reader` on the container to list ([restore.md](../runbooks/restore.md) prerequisites): if `az` answers `AuthorizationPermissionMismatch`, grant it, wait a minute, retry.

**If the upload fails:** `ERROR: Failed to resolve tenant ''` means the workload identity webhook did not inject the token: check the AKS cluster has the OIDC issuer and workload identity enabled (Terraform), and that the ServiceAccount `postgres-backup` carries the client id annotation: `kubectl -n $NS get sa postgres-backup -o yaml`.

Clean up the manual Job: `kubectl -n $NS delete job backup-manual`.

## data-4: restore from the backup (disaster drill)

**Why:** a backup nobody restored is not a backup. Follow [restore.md](../runbooks/restore.md) literally; this test checks that the runbook is correct and gives the recovery time.

1. Right after data-3's backup, screenshot the result page: this is the state the backup holds.
2. Vote **SaltStack** from 3 private windows. The result page shows the screenshot's total + 3. These votes are newer than the backup: they will be lost, by design.
3. Simulate the disaster (someone drops the table):
   ```sh
   kubectl -n $NS exec postgres-0 -- sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP TABLE votes"'
   ```
   Start a stopwatch. Watch the browser: the result page freezes or goes white; terminal B shows worker and result restarting in a loop. Vote **Chef** from 2 private windows now: poll gives ✔ (it only needs Redis). The worker takes each vote off the queue, fails to write it (no table), **pushes it back** onto the queue and exits; the restarted worker tries again. The votes wait in Redis until the table is back.
4. Execute steps 1 to 4 of the runbook literally (pick the blob, download, `kubectl cp`, `pg_restore --clean --if-exists --no-owner`, verify).
5. Watch the result page come back (reload once if it stays white). Stop the stopwatch.

**Expect:** `pg_restore` ends without error; worker and result recover by themselves; the result page shows the **screenshot's numbers plus the 2 Chef votes of step 3** (they waited in Redis), and **without** the 3 SaltStack votes of step 2: that is the accepted loss of up to 6 hours. Record the stopwatch time: the recovery time for the Q&A.

**If a runbook step does not work as written:** fix the runbook in the same PR as the run. That is the point of the test.

## data-5: the 7-day expiry rule exists

```sh
az storage account management-policy show --account-name $ACCOUNT -g $AKS_RESOURCE_GROUP --query 'policy.rules[].{name:name,days:definition.actions.baseBlob.delete.daysAfterModificationGreaterThan}' -o table
```

**Expect:** one rule deleting blobs after `7` days. (If the storage account is in another resource group, replace `-g`; `terraform output` shows it.) Waiting a week to see a deletion is not part of this suite.

## data-6: disks and cost match the estimate

```sh
kubectl get pv -o custom-columns=NAME:.metadata.name,SIZE:.spec.capacity.storage,CLAIM:.spec.claimRef.name,CLASS:.spec.storageClassName
az disk list -g "$(az aks show -g $AKS_RESOURCE_GROUP -n $AKS_NAME --query nodeResourceGroup -o tsv)" --query '[].{name:name,sizeGb:diskSizeGb,sku:sku.name}' -o table
```

**Expect:** exactly two data disks (PostgreSQL, Redis) besides the node OS disks, matching the count [cost.md](../cost.md) assumes. A third disk is an unexpected billed item: investigate before leaving the cluster stopped.
