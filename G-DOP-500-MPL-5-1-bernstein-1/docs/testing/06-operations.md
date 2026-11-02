# 6. Operations

Day-two actions: rollback, CI deploy, uninstall, cluster power, and the full rehearsal on a cluster our Terraform did not create. Run this file last: it ends with the cluster stopped.

## ops-1: manual rollback

**Why:** the fastest answer to "your new version is broken, what do you do?".

1. Ship a "bad version" (a visible wrong label):
   ```sh
   helm -n $NS history bernstein | tail -4
   helm -n $NS upgrade bernstein charts/bernstein --reuse-values --set poll.options.a=Broken --wait
   ```
2. Reload the poll page: the first button reads **Broken**. That is the bug a visitor reports.
3. Start the checker in C. Keep the poll page open and reload it every few seconds during the next step.
4. Terminal A, roll back to the revision before:
   ```sh
   PREV=$(helm -n $NS history bernstein -o json | jq '.[-2].revision')
   helm -n $NS rollback bernstein $PREV --wait
   helm -n $NS history bernstein | tail -2
   ```
5. Ctrl-C the checker.

**Expect:** the button reads **Ansible** again after the rollback, and the footer shows new pod names: the rollback is a rolling update too. The page answered at every reload; the checker reports **0 errors**. `helm history` shows a new revision described `Rollback to N`.

## ops-2: release history is bounded

```sh
kubectl -n $NS get rs -l app.kubernetes.io/component=poll | wc -l
```

**Expect:** at most 6 lines (header + `revisionHistoryLimit: 5`), however many upgrades you ran today.

## ops-3: the namespace guard rails exist

```sh
kubectl -n $NS get limitrange,resourcequota
kubectl -n $NS run probe --image=busybox:1.37 --restart=Never -- sleep 30
kubectl -n $NS get pod probe -o jsonpath='{.spec.containers[0].resources}'; echo
kubectl -n $NS delete pod probe
```

**Expect:** one LimitRange and the `compute` ResourceQuota; the hand-started pod received the LimitRange defaults (`requests` `cpu: 50m`, `memory: 64Mi`; `limits` `cpu: 200m`, `memory: 128Mi`). Without the LimitRange the quota would have refused it.

## ops-4: CI deploys on merge to `main`

**Why:** acceptance criterion of #24; it only runs on a push to `main`, so it is tested with a release PR (#40) or by re-running the last run.

```sh
gh run list --workflow release-images.yml --branch main --limit 3
gh run view <run id> --log | grep -E 'poll:|result:' | tail -2     # or open the run summary page
helm -n $NS history bernstein | tail -2
kubectl -n $NS get deploy poll -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
git rev-parse origin/main
```

To trigger without a new merge: `gh run rerun <id of the last main run>`.

Open the two URLs from the job summary in the browser, vote once, check the result page.

**Expect:** the `deploy` job is green and the job summary lists the two URLs; they open the working application (vote counted, result page live); the latest Helm revision is that deploy; the poll image tag equals `git rev-parse origin/main`. The run used the `production` environment (shown on the run page) and no secret appears in the log (`gh run view --log | grep -c "$POSTGRES_PASSWORD"` is `0`).

**Also check the gate:** a run on `dev` has an `image` job but **no** `deploy` job: `gh run list --workflow release-images.yml --branch dev --limit 1` then `gh run view <id>`.

## ops-5: `make destroy` removes everything but the data

```sh
make destroy
kubectl -n $NS get all,cm,secret,pvc
helm -n $NS list
kubectl get gatewayclass traefik; kubectl -n traefik get svc traefik
```

**Expect:** `helm list` is empty; only the PVCs (and the default `kube-root-ca.crt` ConfigMap and possibly the namespace's default ServiceAccount) remain; the Gateway class and Traefik are still there (cluster-wide, [ADR-0003](../adr/0003-gateway-prerequisites-outside-chart.md)). The script told you the disks are still billed.

Do **not** run `DELETE_PVC=1` unless you are about to run the rehearsal from scratch (ops-7): it deletes the votes.

Redeploy afterwards with `make deploy` (the same password; data-2 shows the data comes back).

## ops-6: cluster stop and start keep everything

**Why:** the cost routine relies on it: a stopped cluster keeps workloads and disks.

1. Screenshot the result page; keep the browser tabs open.
2. Terminal A:
   ```sh
   make cluster-stop                 # about 5 minutes; billing of the nodes stops
   make cluster-status               # power: Stopped
   ```
3. Reload both pages: they no longer load (the nodes are off).

If this is the end of the session, **stop here**: the test resumes at the next session start, from step 4.

4. Terminal A:
   ```sh
   make cluster-start                # about 5-10 minutes; billing starts
   kubectl -n $NS get pods
   kubectl -n $NS get gateway -o jsonpath='{.items[0].status.addresses[0].value}'; echo
   ```
5. Reload the **same tabs** (same URLs as before the stop). Vote once.

**Expect:**
- step 2: `power: Stopped`; step 3: the pages time out;
- step 4: all pods `1/1` without any `make deploy` (allow a few minutes and some restarts of worker/result while the databases come up). The printed IP is **the same** as before;
- step 5: the old URLs work, the result page matches the screenshot, the new vote is counted. If the IP changed, the bookmarked URLs are dead: record it (it matters for the defense) and run `make deploy` to move the routes to the new `<ip>.nip.io`.

## ops-7: full rehearsal on a cluster our Terraform did not create (#39)

**Why:** the defense may hand you the evaluator's AKS. Everything above ran on our cluster, where Terraform already granted AcrPull and Traefik may be installed. This test removes both advantages. It costs money (a second cluster): run it **once**, as short as possible, and delete the cluster at the end. Agree on it as a team first.

1. Create a minimal throw-away cluster **outside Terraform** (same region and VM size as ours to stay within quota; our cluster must be **stopped** first because the vCPU quota does not fit both, see [infra/terraform/CLAUDE.md](../../infra/terraform/CLAUDE.md)):
   ```sh
   make cluster-stop
   az group create -n bernstein-rehearsal-rg -l <our region>
   az aks create -g bernstein-rehearsal-rg -n rehearsal --node-count 2 --node-vm-size <our size> --generate-ssh-keys --tier free
   ```
2. Use a fresh clone of the repository, a fresh shell, only the documented variables:
   ```sh
   git clone <repo url> /tmp/rehearsal && cd /tmp/rehearsal && nix develop
   export AKS_RESOURCE_GROUP=bernstein-rehearsal-rg AKS_NAME=rehearsal ACR_NAME=<our acr> POSTGRES_PASSWORD='<new one>'
   time make deploy
   ```
3. Run, against the printed URLs: `deploy-3`, `deploy-4`, `func-1`, `func-3`, `res-2`.
4. Delete the cluster: `az group delete -n bernstein-rehearsal-rg --yes --no-wait`. Check after ~10 min that `az group list -o table` no longer shows it (and its `MC_` group).

**Expect:** the deploy log shows `Granting AcrPull on <acr> to the cluster` and `Installing Gateway API and Traefik`; the deploy finishes in one command with no manual step; the five tests pass. Record the total time from `make deploy` to both URLs answering: the number for the defense.

**If anything needed a manual step:** that step is a bug in `deploy.sh` or in the from-scratch guide (#36). Open an issue.

## ops-8: end of session

```sh
make cluster-stop
make cluster-status
```

**Expect:** `power: Stopped`. Write the session's cluster uptime in the result sheet (start and stop times) so the spend can be compared with [cost.md](../cost.md).
