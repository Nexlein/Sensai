# Restore the PostgreSQL database from a backup

When: the votes table is damaged or gone (bad `DROP TABLE`, PVC deleted, disk lost). Backups are written every 6 hours by the `postgres-backup` CronJob, see [postgres.md](../postgres.md#backups).

Prerequisites: `az login`, `kubectl` on the cluster, and your user needs `Storage Blob Data Reader` on the container (`az role assignment create --role "Storage Blob Data Reader" --assignee <you> --scope <container id>`).

## 1. Pick a backup

```sh
ACCOUNT=$(terraform -chdir=infra/terraform output -raw backup_storage_account)
CONTAINER=$(terraform -chdir=infra/terraform output -raw backup_container)
az storage blob list --auth-mode login --account-name "$ACCOUNT" -c "$CONTAINER" --query '[].name' -o tsv
```

Names are UTC timestamps (`20261013T120000Z.pgdump`): the last one is the newest. Blobs older than 7 days are gone.

## 2. Download it

```sh
BLOB=20261013T120000Z.pgdump
az storage blob download --auth-mode login --account-name "$ACCOUNT" -c "$CONTAINER" -n "$BLOB" -f "/tmp/$BLOB"
```

## 3. Restore into the running database

If the PVC was deleted, run `make deploy` first so an empty `postgres-0` exists (initdb creates the database and schema).

```sh
kubectl -n bernstein cp "/tmp/$BLOB" postgres-0:/tmp/restore.pgdump
kubectl -n bernstein exec postgres-0 -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner /tmp/restore.pgdump && rm /tmp/restore.pgdump'
```

`--clean --if-exists` drops each object before recreating it, so it works on a damaged database and on a fresh one. Worker and result exit on a database error and restart by themselves, so no restart is needed.

## 4. Verify

```sh
kubectl -n bernstein exec postgres-0 -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT vote, count(*) FROM votes GROUP BY vote"'
```

The counts must match the result page. Votes cast after the backup are lost: at most 6 hours.

## Tested

2026-10-13, on a local kind cluster (not AKS):

- The CronJob, ServiceAccount and a Job created with `kubectl create job --from=cronjob/postgres-backup` ran. The `dump` init container produced `/backup/dump.pgdump` (`-rw-r--r-- 1 postgres postgres 1638`).
- Three votes inserted (`cats` 2, `dogs` 1), dump taken with the same `pg_dump -Fc`, `DROP TABLE votes`, then step 3 above (`kubectl cp` + `pg_restore --clean --if-exists --no-owner`): `SELECT vote, count(*)` returned `cats` 2, `dogs` 1 again.
- The `upload` container failed on kind with `ERROR: Failed to resolve tenant ''` and `cat: '': No such file or directory`: there is no workload identity webhook there, so `AZURE_TENANT_ID` and `AZURE_FEDERATED_TOKEN_FILE` are empty. Expected.

**Not yet tested**: the upload to Blob and the download in step 2 on AKS. To do at sprint end, after `terraform apply` and `make cluster-start`; then replace this line with the result.
