# 4. Resilience and zero downtime

The graded part of the defense: a service is updated while the application is used, and nothing must fail. Each test here is done twice at once:

- **as a visitor**, in the browser: you keep voting and watching the result page during the disruption, as the jury will;
- **with the checker** in terminal C (`scripts/zero-downtime-check.sh`, [zero-downtime-check.md](../zero-downtime-check.md)), because a human misses an outage of 200 ms. It requests the four things a visitor's browser requests (poll page, a vote, result page, the Socket.IO handshake) ten times a second, prints every failure, and prints a report when stopped.

Both must agree: the browser shows what the jury sees, the checker report is the evidence.

The checker **casts real votes**: while it runs, the result total climbs by itself (about 10 votes a second). Tests that count votes exactly say *stop the checker* first.

Layout ([README](README.md#screen-layout)): browser with poll and result side by side, **A** commands, **B** `kubectl -n $NS get pods -w`, **C** checker.

```sh
# terminal C, start it when a test says "checker running"; Ctrl-C prints the report
scripts/zero-downtime-check.sh $POLL $RESULT 0
```

## res-1: baseline, nothing broken

**Why:** know what "normal" looks like, in the browser and in the report, before breaking anything.

1. Start the checker in C.
2. In the browser, for one minute: vote, change your vote, reload the poll page, watch the result page climb (the checker's votes).
3. Ctrl-C the checker.

**Expect:**
- browser: every click gives ✔, the result total grows smoothly every second, the page never goes white;
- report: four probes (`poll-get`, `poll-post`, `result-get`, `result-socketio`), `0` errors, `OK: no error in N requests`, p95 under about 300 ms. Note the p95 values: they are the reference for the next tests.

## res-2: update poll while voting (the defense scenario)

**Why:** the subject's demonstration: change a service's source, redeploy, and nobody notices.

`make zdt-demo` does the whole scenario: it copies poll, adds `(demo-<timestamp>)` to the page footer, builds and pushes the image, starts its own checker, runs `helm upgrade`, and prints the checker report. **Do not start a checker in C** for this test.

1. Poll page open, footer visible: *Processed by container ID poll-...*. Note the two pod names (reload a few times).
2. Terminal A: `make zdt-demo`.
3. During the whole run (2-3 minutes: build, then rollout), keep using the poll page: click a different option every few seconds and reload. Keep an eye on the result page.
4. Watch terminal B at the same time.

**Expect:**
- **browser**: every click and reload works, no error page, no spinner longer than a second. At some point the footer shows a **new pod name** followed by `(demo-<timestamp>)`: you are now served by the new version, without having seen any interruption. The result page keeps updating;
- **B**: a third poll pod appears (surge), becomes `1/1`, then an old pod goes `Terminating`; the same again for the second pod (`maxUnavailable: 0`, `maxSurge: 1`). About 30-40 s per pod ([ADR-0005](../adr/0005-zero-downtime-rolling-updates.md));
- **report** at the end of `make zdt-demo`: `OK`, **0 errors** on all four probes. Record the rollout duration.

Bring the normal image back afterwards: `make deploy` (the footer loses the demo tag; watch it happen, still with no error).

**If errors appear:** compare the `FAIL` timestamps with B. Status `000` or `502` when an old pod terminates means Traefik still sent it requests after it stopped: preStop sleep too short or missing (compare with res-4).

## res-3: update result and worker while voting

**Why:** the same guarantee for the two other services.

**result:**

1. Checker running in C. Result page open, Network tab (F12) filtered on `socket.io`.
2. Terminal A: `kubectl -n $NS rollout restart deploy/result && kubectl -n $NS rollout status deploy/result`.
3. Watch the result page during the rollout; vote twice from the poll page.
4. When `rollout status` returns, reload the result page once. Ctrl-C the checker.

**Expect:** the result page **never goes white** and keeps updating through the rollout (when the pod holding your session leaves, Traefik sends you to a remaining pod and gives you a new `bernstein_result` cookie; Socket.IO reconnects by itself: you may see one red request in the Network tab, then 200s again). Your two votes appear. Report: 0 errors. A single `502` on `result-get` right at a pod switch was seen once on kind ([gateway.md](../gateway.md)): if it appears, record it with its timestamp; it is a FAIL to investigate, not to ignore.

**worker** (no page of its own; a visitor only sees it through the result page). Stop the checker for this one, its votes would hide yours.

1. Note the result total `T`.
2. Terminal A: `kubectl -n $NS rollout restart deploy/worker`.
3. Right away, vote from 5 private windows, one vote each, while B shows the worker pods being replaced.
4. Wait until B shows both new worker pods `1/1`.

**Expect:** the result total reaches exactly **`T + 5`**. The votes cast while a worker was restarting were not lost.

## res-4: the test can fail (negative control)

**Why:** acceptance criterion of #27: without the zero-downtime settings, the same update must visibly fail; otherwise the green runs above prove nothing.

1. Edit `charts/bernstein/templates/poll/deployment.yaml` **in your working copy only** (never commit it): set `maxUnavailable: 1` and delete the `lifecycle:` / `preStop:` block.
2. Checker running in C. Poll page open.
3. Terminal A:
   ```sh
   helm -n $NS upgrade bernstein charts/bernstein --reuse-values --set-string poll.options.b=Chef-$(date +%s) --wait
   ```
   (the changed label forces a rollout).
4. During the rollout, reload and vote on the poll page as fast as you can.
5. Ctrl-C the checker. Then **restore**: `git checkout charts/bernstein/templates/poll/deployment.yaml && make deploy`.

**Expect:** this time the report has `FAIL` lines on `poll-get` / `poll-post` (status `000`, `502` or `503`) and says `FAILED`. In the browser you may catch an error page or a reload that hangs; you may also miss it, which is exactly why the checker exists. After the restore, the button reads Chef again.

If the report still says 0 errors, lower the interval (`INTERVAL=0.02 scripts/zero-downtime-check.sh ...`) and retry once; record the outcome honestly either way.

## res-5: a pod dies

**Why:** self-healing. Kubernetes replaces a lost pod with no human action.

1. Checker running in C. Poll page open.
2. Terminal A, one component at a time, 30 s apart:
   ```sh
   kubectl -n $NS delete "$(kubectl -n $NS get pod -l app.kubernetes.io/component=poll -o name | head -1)" --wait=false
   kubectl -n $NS delete "$(kubectl -n $NS get pod -l app.kubernetes.io/component=result -o name | head -1)" --wait=false
   kubectl -n $NS delete "$(kubectl -n $NS get pod -l app.kubernetes.io/component=worker -o name | head -1)" --wait=false
   ```
3. Keep voting and reloading in the browser meanwhile; watch the poll footer.
4. Then the brutal version, as if the process crashed (no grace period, no preStop):
   ```sh
   kubectl -n $NS delete "$(kubectl -n $NS get pod -l app.kubernetes.io/component=poll -o name | head -1)" --grace-period=0 --force
   ```
5. Ctrl-C the checker.

**Expect:**
- browser: the poll footer shows a pod name you have not seen before (the replacement) within about 30 s of each deletion; no error page for the graceful deletions;
- B: each deleted pod is replaced at once, `1/1` within about 30 s;
- report: **0 errors** for the graceful deletions. The forced kill may cost a few failed requests (those in flight on the killed pod): record how many and when. That number answers "what if a pod crashes?" at the defense.

## res-6: a node is drained (the question every jury asks)

**Why:** "what happens if we drain this node?" ([helm-availability.md](../helm-availability.md)). This test also measures the failover time that document lists as "not measured yet".

1. Terminal A: `kubectl -n $NS get pods -o wide`. Note which node holds `postgres-0` and `redis-0`, and which holds no database (if both nodes hold one, do only step 2 with either).
2. **Drain the node holding the databases.** Checker running in C, poll and result open.
   ```sh
   NODE=<node name>
   date +%T; kubectl drain $NODE --ignore-daemonsets --delete-emptydir-data --timeout=10m; date +%T
   ```
   Keep voting every 10 seconds and watching both pages during the drain.
3. When the drain returns: Ctrl-C the checker, `kubectl -n $NS get pods -o wide`, then `kubectl uncordon $NODE`.
4. If a node held no database, repeat steps 2-3 on it.

**Expect:**
- the drain **finishes** (databases have no PodDisruptionBudget on purpose; poll, result and worker each keep one pod until its replacement is ready);
- `postgres-0` and `redis-0` restart on the other node with their disks (1-3 minutes: the Azure disk detaches and reattaches);
- **browser during the database move**: the poll page may show an error page (no poll pod ready while Redis is away) and the result page may freeze or go white (result restarts while PostgreSQL is away). Both come back **by themselves** when the databases are up. The votes you cast and got a ✔ for are all on the result page afterwards;
- **report**: errors only during the database move. Record the **first and last `FAIL` timestamps** (the visitor-visible outage) and the drain duration (the two `date` outputs);
- **drain of a node without databases** (step 4): the browser never shows an error and the report says **0 errors**.

Paste the measured numbers into [helm-availability.md](../helm-availability.md) in the same PR as the run.

**If the drain hangs:** `kubectl -n $NS get pdb` shows `ALLOWED DISRUPTIONS 0`: a pod of that component is not ready, or its replacement cannot fit on the remaining node (`kubectl -n $NS describe pod <Pending pod>`).

## res-7: a database dies

**Why:** worker and result exit on any database error and rely on Kubernetes restarting them; the databases restart on their disks.

**PostgreSQL** (stop the checker; count votes by hand):

1. Note the result total `T`.
2. Terminal A: `kubectl -n $NS delete pod postgres-0`. Start a stopwatch.
3. Immediately, vote from 3 private windows. The poll page gives ✔ each time (poll only needs Redis).
4. Watch the result page and B.

**Expect:** the result page freezes or goes white for a while (result pods restart, `RESTARTS` +1 in B: normal); the poll page keeps working throughout. When `postgres-0` is `1/1` again, the result page comes back by itself (reload once if it stayed white) and shows **`T + 3`**: the votes waited in Redis. Record the time until the result page is back.

**Redis:**

1. Note the result total `T`.
2. Terminal A: `kubectl -n $NS delete pod redis-0`.
3. Reload the poll page every 5 seconds.

**Expect:** the poll page is unavailable (error page) for the few seconds Redis takes to restart, then works again by itself; the result page keeps showing `T` the whole time. Vote once when poll is back: `T + 1`. No manual action anywhere. Record the outage duration.

## res-8: autoscaling under a crowd

**Why:** the "scalable" requirement. The autoscaler adds poll pods when their CPU is high. Only poll autoscales by default.

1. Terminal A: `kubectl -n $NS get hpa poll`. `TARGETS` must be a number like `2%/70%`. If it shows `<unknown>/70%`, stop: fail the test and open an issue (metrics missing).
2. Terminal B: `kubectl -n $NS get hpa poll -w`.
3. Terminal C, start the crowd (40 parallel visitors loading the page without pause):
   ```sh
   for j in $(seq 40); do ( while true; do curl -s -o /dev/null $POLL/; done ) & done
   ```
4. In the browser, reload the poll page every 20 seconds and note the pod names in the footer. Vote now and then.
5. After 5 minutes, or when `REPLICAS` reaches 5: stop the crowd in C with `kill $(jobs -p)`.
6. Keep B open 5 more minutes.

**Expect:**
- within 1-3 minutes `TARGETS` goes above `70%` and `REPLICAS` rises from 2 towards 5;
- the poll footer shows **new pod names**, up to five different ones; the page stays fast and votes still get ✔;
- after the crowd stops, about 2 minutes later (scale-down window) `REPLICAS` goes back to 2;
- `kubectl -n $NS get pods -l app.kubernetes.io/component=poll` never shows a `Pending` pod (if one does: quota or node capacity, `kubectl -n $NS describe pod <pod>`).

If the crowd is too small to move `TARGETS`, raise 40 to 100. Record the peak replica count, time to scale up and time to scale down.

Optional: run the checker in C during scale-down (after `kill $(jobs -p)`): removing pods must cause **0 errors**.

## res-9: the quota stops a runaway

**Why:** a mistake (or a hostile scale) must not eat the whole cluster.

```sh
kubectl -n $NS describe resourcequota compute
kubectl -n $NS scale deploy/worker --replicas=40
sleep 20
kubectl -n $NS get events --sort-by=.lastTimestamp | grep -i quota | tail -3
kubectl -n $NS get deploy worker
kubectl -n $NS scale deploy/worker --replicas=2
```

**Expect:** events say `exceeded quota: compute`; `get deploy worker` shows far fewer than 40 ready pods. Meanwhile the browser still works normally (vote once). After scaling back to 2, all is stable. (A manual scale is undone by the next `helm upgrade` anyway; this test is about the quota.)
