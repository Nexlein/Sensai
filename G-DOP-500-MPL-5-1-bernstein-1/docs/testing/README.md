# Manual test suite

Human-driven acceptance tests for the whole deployment. There is no automated test suite in this repository (CI only lints and builds); this suite is what proves, before the defense, that every acceptance criterion holds on a real cluster.

**The application is tested the way a visitor uses it: in a browser.** You vote by clicking on the poll page and you read the outcome on the result page, as the jury will. The terminal is only used for what a visitor cannot do: deploying, breaking things on purpose (kill a pod, drain a node), and two tools that a human cannot replace, listed below.

## How a test is written

Every test has the same five parts, so none needs interpretation under pressure:

| Part | Meaning |
|---|---|
| **ID** | `<area>-<n>`, used in the result sheet and in bug reports. |
| **Why** | The requirement or failure it covers. |
| **Do** | Browser steps (numbered) and operator commands to paste. |
| **Expect** | The exact observable result, on screen or in the terminal. If it differs, the test fails. |
| **If it fails** | The first thing to look at. |

A test passes only if **Expect** is observed. "It seemed to work" is a fail: write what you saw.

## What the application shows

Learn these before testing: they are the signals every test reads.

**Poll page** (`http://poll.<ip>.nip.io`):

- Title *What's your favorite DevOps tool?* and four buttons: Ansible, Chef, Puppet, SaltStack.
- After a click, the page reloads: the chosen button is greyed out with a check mark ✔, the three others are faded. That means poll accepted the vote and queued it in Redis.
- *(Tip: you can change your vote)*: clicking another button replaces your vote, it does not add one.
- Footer: **`Processed by container ID poll-xxxxxxxxx-yyyyy`**: the name of the pod that answered. Reloading several times shows both pods' names (load balancing), and during an update the names change to the new pods'. This is how you see a rollout from the browser.
- You are one voter per browser, identified by the `voter_id` cookie. **A private (incognito) window is a new voter**; closing it and opening a new one is another new voter.

**Result page** (`http://result.<ip>.nip.io`):

- The four options with a percentage each, coloured blocks sized by the score, and at the bottom the total: `No votes yet`, `1 vote` or `N votes`.
- It updates **by itself** about once a second (Socket.IO, long polling): never reload it to see a new vote.
- **A blank page means Socket.IO is broken.** The page is invisible until the first Socket.IO message arrives, so a white page that stays white is the failure the sticky session prevents.
- Labels on the result page are written in the page itself, not read from the chart: see the known gaps.

## Browser setup

- One normal window with two tabs: poll and result, side by side if possible, so a click on one is seen on the other.
- Private windows for extra voters (Ctrl+Shift+N in Chrome, Ctrl+Shift+P in Firefox).
- Developer tools (F12) only where a test asks for them: **Network** tab to see requests and their status, **Application** (Chrome) or **Storage** (Firefox) tab to see cookies.
- Disable the browser cache while testing updates: Network tab, tick *Disable cache* (keep the tools open).

## The two scripted tools

A human cannot request a page ten times a second for ten minutes, nor be a crowd. Two tools do that; you still read the application while they run.

| Tool | Used in | Why a human cannot do it |
|---|---|---|
| `scripts/zero-downtime-check.sh` | file 4 | The defense judges zero downtime by requesting the application continuously; a 200 ms outage is invisible to a human reloading the page. It prints every failed request and a final report. **It casts real votes**: the result total grows while it runs. |
| a `curl` loop as a crowd | `res-8` | The autoscaler only reacts to dozens of requests per second. |

## The files

Run them in this order; each assumes the previous ones passed.

| # | File | Needs a cluster | Content |
|---|---|---|---|
| 1 | [01-static.md](01-static.md) | no | Lint, render, schema validation, Terraform validate, secrets scan: what CI does, run by hand |
| 2 | [02-deploy.md](02-deploy.md) | yes | `make deploy` on a fresh namespace, idempotence, failure paths, password handling |
| 3 | [03-functional.md](03-functional.md) | yes | In the browser: vote, change a vote, many voters, live result page, load balancing, sticky sessions, Redis outage as a visitor sees it, configuration change |
| 4 | [04-resilience.md](04-resilience.md) | yes | Updates while voting (zero downtime), test that can fail, pod kills, node drain, database loss, autoscaler under load |
| 5 | [05-data.md](05-data.md) | yes | Persistence across restarts, backup CronJob, restore |
| 6 | [06-operations.md](06-operations.md) | yes | Rollback, quota, CI deploy, `destroy`, cluster stop/start, evaluator's-cluster rehearsal |
| - | [results-template.md](results-template.md) | - | Copy it per run; one line per test |

## Before you start

### Cost: read this

The cluster is billed from the moment it starts. [cost.md](../cost.md) leaves almost no headroom (~56 € expected against a 60 € budget). Rules for a test session:

- Run files 2 to 6 **in one sitting**, then `make cluster-stop`. Every extra hour of two nodes is 0.308 €.
- File 1 needs no cluster at all: do it first, on any day.
- Start the cluster only when you are ready to run the tests: `make cluster-start` (waits until the nodes are Ready). A stopped cluster keeps its workloads and disks, so nothing is redeployed.
- Test `06-operations` last: it ends with the stop/start test and the final `make cluster-stop`.
- Expected duration: about 3 hours for files 2 to 6.

### Tools

From the repository root, in the Nix dev shell (`nix develop`, or direnv). Check:

```sh
for t in az terraform kubectl helm docker gh jq curl; do command -v $t >/dev/null && echo "ok  $t" || echo "MISSING $t"; done
```

Expect eight `ok` lines. `kubeconform` is fetched on demand by `nix shell nixpkgs#kubeconform`.

### Session variables

Paste once per terminal. Every later command uses them.

```sh
export AKS_RESOURCE_GROUP=bernstein-rg
export AKS_NAME=bernstein-aks
export ACR_NAME=<acr name, no .azurecr.io>        # terraform -chdir=infra/terraform output
export POSTGRES_PASSWORD='<choose one, never commit it>'
export NS=bernstein
# Chart flags used by the offline tests:
export OK="--set global.registry=example.azurecr.io --set-string global.tag=dev --set-string postgres.password=dev"
```

After `make deploy` (file 2), also:

```sh
export IP=$(kubectl -n $NS get gateway -o jsonpath='{.items[0].status.addresses[0].value}')
export POLL=http://poll.$IP.nip.io
export RESULT=http://result.$IP.nip.io
echo $POLL $RESULT
```

Open the two printed URLs in the browser (see [Browser setup](#browser-setup)).

### Screen layout

Most tests of files 3 to 6 combine the browser and up to three terminals: the browser with poll and result side by side, and a terminal multiplexer with three panes: **A** for commands, **B** for `kubectl -n $NS get pods -w` (shows pods appearing and terminating, the "backstage" of what the browser shows), **C** for the zero-downtime checker.

### Recording

Copy [results-template.md](results-template.md) to `docs/testing/runs/<date>-<name>.md` (untracked or committed, your choice), fill one line per test: `PASS`, `FAIL` or `SKIP` with the evidence (a number, a pasted line). Anything that fails becomes a GitHub issue with the test ID in the title, using the `issue-format` conventions.

## What the suite does not cover

- Application code correctness: the application is provided and fixed.
- Penetration testing. #32 to #34 (network policies, security contexts, RBAC) are not merged yet; when they are, add a `07-security.md` here.
- Observability (#35), for the same reason.

## Known gaps found while writing this suite

Things the suite will trip over unless fixed; each is a candidate issue of the sub-sprint.

| Gap | Effect on the tests |
|---|---|
| `postgres.backup.enabled` defaults to `false` | Fixed by #73: `make deploy` enables backups when `BACKUP_STORAGE_ACCOUNT`, `BACKUP_CONTAINER` and `BACKUP_CLIENT_ID` are set; test `data-3` uses it. Without them, no backup. |
| The result page's labels are hardcoded in `result/views/index.html` (Ansible, Chef, Puppet, SaltStack); `poll.options` only changes the poll page | After `func-8` the two pages disagree: the poll page says *Terraform*, the result page still says *Ansible* for the same vote. The application code is fixed, so this is a limit to state at the defense, not to fix: change `poll.options` only for the demo of a configuration rollout, and change it back. |
| `result.autoscaling.enabled` is `false` | Only poll autoscales. Test `res-8` checks poll only. |
| Backup upload and restore download are "not yet tested on AKS" ([restore.md](../runbooks/restore.md)) | `data-3` and `data-4` are the first real run. |
| Node-drain failover time is "not measured yet" ([helm-availability.md](../helm-availability.md)) | `res-6` and `res-7` produce the number; paste it into those documents. |
