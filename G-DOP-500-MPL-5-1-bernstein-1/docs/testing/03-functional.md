# 3. Functional tests: using the application

Proves the application works end to end, as a visitor sees it: a click on the poll page travels `poll --(RPUSH)--> Redis --(BLPOP)--> worker --(UPSERT)--> PostgreSQL <--(SELECT)-- result` and shows up on the result page. Read [What the application shows](README.md#what-the-application-shows) first.

Setup for the whole file: browser window with **poll** (`$POLL`) and **result** (`$RESULT`) side by side; terminal B running `kubectl -n $NS get pods -w`.

Write down the result page total at the start of each test: every expectation below is relative to it.

## func-1: first vote

**Why:** the core feature, from a visitor's point of view.

1. On the result page, note the total at the bottom (`No votes yet` on a fresh install) and the four percentages.
2. On the poll page, click **Ansible**.
3. Look at the poll page, then at the result page **without reloading it**.

**Expect:**
- the poll page reloads; *Ansible* is greyed out with a check mark ✔, Chef, Puppet and SaltStack are faded;
- within about 2 seconds the result page shows the total **+1** and the Ansible percentage and block grow. On a fresh install: `1 vote`, Ansible `100.0%`, the others `0.0%`.

**If the result page does not move:** the chain is broken somewhere after poll. Backstage, in that order: `kubectl -n $NS logs deploy/worker --tail=20` (cannot reach Redis or PostgreSQL?), `kubectl -n $NS logs deploy/result --tail=20`. A result page that is **blank** is a Socket.IO problem, not a vote problem: see func-5.

## func-2: changing your vote

**Why:** the page says *you can change your vote*: one visitor is one vote, the latest one counts.

1. Same window as func-1. Note the result total.
2. On the poll page click **Chef**. Wait 2 seconds, look at the result page.
3. Click **Puppet**. Wait, look again.

**Expect:**
- after each click the poll page marks the new choice with ✔ (Chef, then Puppet);
- the result **total does not change** (still the number noted in step 1); the percentage moves from Ansible to Chef, then from Chef to Puppet.

**If the total grows at each click:** votes are not keyed by voter (cookie lost, or the upsert is broken): fail.

## func-3: several visitors

**Why:** each browser is a different voter, and every vote counts.

1. Note the result total `T`.
2. Open a **private window**, open `$POLL`, click **SaltStack**, close the private window.
3. Repeat step 2 three more times, choosing SaltStack, SaltStack, Chef.
4. Look at the result page.

**Expect:** total `T + 4`. SaltStack has gained three votes and Chef one. The percentages add up to 100 %.

If two or more people test together, everyone votes from their own laptop or phone at the same time: total grows by the number of people.

## func-4: load balancing is visible

**Why:** two poll pods serve visitors; the footer shows which one answered.

1. On the poll page, reload 10 times (F5) and read the footer *Processed by container ID ...* each time.
2. In terminal A: `kubectl -n $NS get pods -l app.kubernetes.io/component=poll`.

**Expect:** the footer shows **two different names** across the reloads, and they are exactly the two pod names listed by `kubectl`. (The browser may keep one connection open and stick to one pod for a few reloads; a private window or waiting a few seconds between reloads helps.)

## func-5: the result page stays live (sticky sessions)

**Why:** result runs two pods. Socket.IO's long-polling requests must all reach the pod that opened the session, or the server answers `400 Session ID unknown` and the page never shows. Traefik's sticky cookie `bernstein_result` guarantees it ([gateway.md](../gateway.md)).

**Positive check:**

1. Reload the result page 10 times. Each time it must appear within a second (not stay white).
2. Open developer tools (F12):
   - **Application** (Chrome) / **Storage** (Firefox) → Cookies → `result.<ip>.nip.io`: a cookie named `bernstein_result`, flagged `HttpOnly`;
   - **Network** tab, filter `socket.io`: a stream of requests about one per second (`?EIO=4&transport=polling&sid=...`), all status **200**.
3. Leave the page open 2 minutes while you vote once from the poll page.

**Expect:** the page always appears, the cookie is there, no `400` in the Network tab during 2 minutes, and the vote shows up.

**Negative check (proves the cookie is what makes it work):**

1. Block cookies for the result site only. Chrome: click the icon left of the address bar → *Site settings* → *Third-party / Cookies and site data* → **Block**, or `chrome://settings/cookies` → *Not allowed to use cookies* → add `result.<ip>.nip.io`. Firefox: padlock icon → *Clear cookies and site data*, then *Settings → Privacy → Cookies → Manage exceptions* → add `http://result.<ip>.nip.io` → **Block**.
2. Reload the result page 5 times, Network tab open.
3. **Remove the block** afterwards and reload: the page works again.

**Expect:** with cookies blocked, on most reloads the page stays **white** or stops updating, and the Network tab shows `socket.io` requests answered **`400`** (response body `{"code":1,"message":"Session ID unknown"}`). The browser may get lucky and hit the same pod twice in a row: one working reload out of five is normal, five out of five means stickiness is not what is being tested (only one result pod running? check `kubectl -n $NS get pods -l app.kubernetes.io/component=result`).

## func-6: what a visitor sees when Redis is down

**Why:** the probe design. Liveness (`/healthz`) ignores Redis, so pods are **not** restarted; readiness (`/readyz`) checks it, so the gateway stops sending visitors to pods that cannot take a vote. This test breaks Redis for about a minute.

1. Note the result total `T`, and the poll pods' `RESTARTS` in terminal B.
2. In the browser, open `$POLL/healthz` and `$POLL/readyz` in two tabs: both show the text `ok`.
3. Terminal A: `kubectl -n $NS scale statefulset redis --replicas=0`.
4. Wait 30 seconds. Reload the poll page, `$POLL/healthz`, and the result page.
5. Terminal A: `kubectl -n $NS scale statefulset redis --replicas=1`.
6. Watch terminal B and reload the poll page every 10 seconds until it is back, then click **Ansible**.

**Expect:**
- step 4: the poll page does **not** load: Traefik shows an error (`no available server` or a 503 page), because no poll pod is ready. Terminal B shows the poll pods `0/1` but their **RESTARTS do not increase**. `$POLL/healthz` also fails through the gateway (no ready pod to route to; it would answer 200 from inside the pod, which is the point). The result page **keeps showing the score** (result does not use Redis);
- step 6: within about a minute of Redis being back, the poll page loads again by itself, with no action from you; the vote shows on the result page (total `T + 1`). Poll restarts: **unchanged**. The worker may show one or two restarts: by design it exits on a Redis error and Kubernetes restarts it.

**If poll pods restart:** liveness is checking Redis; fail and open an issue (a Redis blip would restart every pod). Check with `kubectl -n $NS get deploy poll -o jsonpath='{.spec.template.spec.containers[0].livenessProbe.httpGet.path}'` → must be `/healthz`.

## func-7: votes are not lost while the worker is busy restarting

**Why:** votes wait in Redis when nobody consumes them; the worker catches up.

1. Note the result total `T`.
2. Terminal A: `kubectl -n $NS scale deploy/worker --replicas=0`.
3. In 3 private windows, vote (any option), one per window. The poll page shows ✔ each time: poll accepted the vote.
4. Look at the result page for 30 seconds: total is still `T` (nobody moves votes to PostgreSQL).
5. Terminal A: `kubectl -n $NS scale deploy/worker --replicas=2`.

**Expect:** step 4 total stays `T`; within a few seconds of step 5 (once a worker pod is `1/1` in B) the total jumps to **`T + 3`**. Nothing was lost while the worker was away.

## func-8: configuration change without rebuilding an image

**Why:** the labels of poll are chart values; changing one is a rolling update, no image build.

1. Terminal A:
   ```sh
   helm -n $NS upgrade bernstein charts/bernstein --reuse-values --set poll.options.a=Terraform --wait
   ```
2. While it runs, reload the poll page every few seconds and watch the footer.
3. When it finishes, look at the poll page and the result page.
4. Restore: same command with `--set poll.options.a=Ansible`.

**Expect:**
- during step 2 the footer's pod names change to new ones; the page answers at every reload;
- step 3: the first button now reads **Terraform**. The result page still says **Ansible** for the same option: known limit, the result labels are hardcoded in the application ([README](README.md#known-gaps-found-while-writing-this-suite)). Record `PASS` if the poll button changed;
- after step 4 the button reads Ansible again.
