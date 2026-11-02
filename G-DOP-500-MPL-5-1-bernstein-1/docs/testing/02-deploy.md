# 2. Deploy

Proves the one-command deployment ([deploy.md](../deploy.md)). Start the cluster first (this starts billing, see [README](README.md#cost-read-this)):

```sh
make cluster-start
```

**Expect:** nodes `Ready`, then `power: Running`.

## deploy-1: refuses to run without its inputs

**Why:** a missing password must never reach the cluster.

```sh
env -u POSTGRES_PASSWORD ./scripts/deploy.sh
env -u ACR_NAME ./scripts/deploy.sh
```

**Expect:** `error: POSTGRES_PASSWORD is not set (see docs/deploy.md)` and the same for `ACR_NAME`, exit code 1, nothing printed by `az`.

## deploy-2: from-scratch deploy

**Why:** the defense step "deploy on a fresh cluster". Start from nothing: if a release exists, remove it with `DELETE_PVC=1 make destroy` first (this deletes the votes).

```sh
kubectl get ns $NS 2>&1 | tail -1          # NotFound is the expected start
time make deploy
```

**Expect:**
- progress lines starting with `>>` (credentials, registry check, build or "already in the registry", Gateway, deploy);
- the last two lines: `poll:   http://poll.<ip>.nip.io` and `result: http://result.<ip>.nip.io`;
- exit code 0, in under about 10 minutes (the first run builds three images and creates a load balancer).

Then set `IP`, `POLL`, `RESULT` ([README](README.md#session-variables)).

**If it fails:** `helm -n $NS status bernstein`, `kubectl -n $NS get pods`, `kubectl -n $NS describe pod <pod>`. `ImagePullBackOff` means the AcrPull step was skipped or failed; `Pending` with `exceeded quota` means the ResourceQuota (see `ops-3`).

## deploy-3: every object is healthy

```sh
kubectl -n $NS get pods -o wide
kubectl -n $NS get statefulset,deployment,svc,pvc,hpa,pdb
kubectl -n $NS get gateway,httproute
kubectl -n traefik get svc traefik
```

**Expect:**

| Object | State |
|---|---|
| pods | `poll` ×2, `worker` ×2, `result` ×2, `postgres-0`, `redis-0`, all `Running` and `READY 1/1`; no leftover `Completed` pod (the schema Job is a pre-upgrade hook, absent on first install) |
| NODE column | the two `poll` pods on different nodes, same for `worker` and `result` ([helm-availability.md](../helm-availability.md)) |
| PVC | `data-postgres-0` 5Gi and `data-redis-0` 1Gi, `Bound`, storage class `managed-csi` |
| Services | `poll`, `result`, `postgres`, `redis` (names are fixed); **no** Service of type `LoadBalancer` except Traefik's |
| hpa | `poll` with `TARGETS` like `3%/70%` (a number, **not** `<unknown>`), `MINPODS 2`, `MAXPODS 5` |
| pdb | `poll`, `worker`, `result`, `ALLOWED DISRUPTIONS 1` |
| gateway/httproute | `Programmed=True` / `Accepted=True` |
| traefik Service | one `EXTERNAL-IP` |

Count public IPs (cost rule: a single entry point):

```sh
kubectl get svc -A -o json | jq -r '.items[] | select(.spec.type=="LoadBalancer") | .metadata.namespace + "/" + .metadata.name'
```

**Expect:** exactly one line, `traefik/traefik`.

## deploy-4: open the application

**Why:** the deploy is done when a visitor can use it, not when pods are Running.

1. Open the two URLs printed by `make deploy` in the browser (copy them from the terminal: `http://poll.<ip>.nip.io` and `http://result.<ip>.nip.io`).
2. Open `http://<ip>/` (the bare IP, no name).
3. Open both URLs from a second device on another network (a phone on mobile data).

**Expect:**
- poll: the title *What's your favorite DevOps tool?*, four buttons Ansible, Chef, Puppet, SaltStack, and the footer *Processed by container ID poll-...*;
- result: the four options at `25.0%` each and `No votes yet` at the bottom (fresh install), fading in within a second. **A page that stays white is a failure** (Socket.IO, see func-5);
- the bare IP shows Traefik's `404 page not found`: correct, routes match on the host name ([gateway.md](../gateway.md#traps));
- the phone shows the same two pages: the application is public, not only reachable from your machine.

Do not vote yet: file 3 starts from `No votes yet`.

## deploy-5: the schema exists

**Why:** worker and result are useless without the `votes` table ([postgres.md](../postgres.md)).

```sh
kubectl -n $NS exec postgres-0 -- sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d votes"'
```

**Expect:** a table with columns `id text` (primary key) and `vote text not null`.

## deploy-6: the password is nowhere it should not be

**Why:** subject requirement; the password must exist only in the Secret.

```sh
helm -n $NS get values bernstein                          # user-supplied values
ps -eo args | grep -F -- "$POSTGRES_PASSWORD" | grep -v grep | wc -l   # while a deploy runs, in another terminal
git status --short; git grep -c "$POSTGRES_PASSWORD" || echo "not in repo"
kubectl -n $NS get secret postgres-credentials -o jsonpath='{.data.password}' | base64 -d; echo
kubectl -n $NS get deploy worker -o yaml | grep -i -A3 'POSTGRES_PASSWORD'
```

**Expect:**
- `helm get values` shows `postgres.password` (Helm stores user values in the release Secret; this is accepted and listed in [helm-chart.md](../helm-chart.md#passwords)). Note it so you can answer for it at the defense;
- during a deploy (run `make deploy` in terminal A, the `ps` line in B) the count is `0`: the password is not in the arguments;
- `not in repo`;
- the decoded Secret equals `$POSTGRES_PASSWORD`;
- the worker env var is a `secretKeyRef`, never a literal `value:`.

Redis password: generated on first install and kept on upgrade (checked in `deploy-7`).

## deploy-7: second run is a no-op (idempotence)

**Why:** `deploy.sh` must be safe to run twice, which is what happens when the evaluator re-runs it.

First, in the browser: click **Ansible** on the poll page; the result page shows `1 vote`. Keep both pages open during the second deploy.

```sh
kubectl -n $NS get secret redis-credentials -o jsonpath='{.data.password}' > /tmp/redis-pw.before
kubectl -n $NS get pods -o name | sort > /tmp/pods.before
helm -n $NS history bernstein
time make deploy
kubectl -n $NS get secret redis-credentials -o jsonpath='{.data.password}' | diff - /tmp/redis-pw.before && echo "redis password kept"
kubectl -n $NS get pods -o name | sort | diff - /tmp/pods.before && echo "same pods"
helm -n $NS history bernstein
kubectl -n $NS get pods
```

**Expect:** `redis password kept`; `same pods` (no pod name changed, so no restart); a new Helm revision with status `deployed`; the logs say `already in the registry` for the three images and install nothing in Traefik. All pods keep their AGE. In the browser: the poll footer shows the same pod names as before, and the result page still shows `1 vote`.

**If pods restarted:** a template is not deterministic (random value, timestamp). Diff `helm get manifest` of the two revisions: `helm -n $NS get manifest bernstein --revision N > a; ... M > b; diff a b`.

## deploy-8: schema hook on upgrade

**Why:** an upgrade runs `postgres-schema` (pre-upgrade Job) before the pods change; it is idempotent.

```sh
kubectl -n $NS get events --sort-by=.lastTimestamp | grep -i postgres-schema | tail -5
kubectl -n $NS get job
```

**Expect:** events show the Job created and completed during `deploy-7`; `get job` is empty afterwards (`hook-succeeded` deletes it). The result page still shows `1 vote`: re-applying the schema did not touch the data.

## deploy-9: failed upgrade rolls back by itself

**Why:** `--rollback-on-failure` is the safety net of the demo.

```sh
helm -n $NS history bernstein | tail -2
IMAGE_TAG=doesnotexist make deploy        # an image tag that is not in the registry
```

While it waits (up to 10 minutes), use the application: vote and change your vote on the poll page every minute, watch the result page, and watch `kubectl -n $NS get pods -w` in terminal B.

**Expect:** B shows new pods stuck in `ImagePullBackOff`, but the **browser never notices**: every vote gets ✔, the result page keeps updating, the poll footer only ever shows the old pod names (the broken pods never become ready, so they never receive visitors). Then `deploy.sh` fails; `helm history` shows the failed revision followed by a rollback to the previous one, `kubectl get pods` is all Ready on the previous image.

```sh
kubectl -n $NS get deploy poll -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
```

**Expect:** the image tag from before the failed run.

## deploy-10: wrong password does not corrupt a working database

**Why:** PostgreSQL only reads `POSTGRES_PASSWORD` at the first initialisation; changing it later does not change the stored password. Know the behaviour before the evaluator hits it.

```sh
POSTGRES_PASSWORD=somethingelse make deploy
kubectl -n $NS get pods -w     # ctrl-c after a minute
kubectl -n $NS logs deploy/worker --tail=5
```

Keep the poll and result pages open meanwhile, and vote once during the deploy.

**Expect (record what you see, then restore):** the Secret changes, the worker and result pods roll (the checksum annotation changes) and the new ones fail to authenticate (`password authentication failed for user`) and restart in a loop, because the database still holds the original password. Since the new pods never become ready, the old ones should keep serving: record whether the result page stayed live and whether your vote appeared. The deploy is expected to fail and roll back. Restore with your original `POSTGRES_PASSWORD` and `make deploy`; pods recover.

This documents a real limitation (changing the password requires `ALTER USER`), useful for the Q&A sheet (#38). It is not a pass/fail test: record `OBSERVED` with the behaviour.
