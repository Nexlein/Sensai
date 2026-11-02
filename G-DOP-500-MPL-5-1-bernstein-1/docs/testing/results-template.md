# Test run: <date>, <tester>

Copy to `docs/testing/runs/<YYYY-MM-DD>-<name>.md`. Result: `PASS`, `FAIL`, `SKIP` or `OBSERVED` (behaviour recorded, no pass/fail). Evidence: a number, a pasted line, an issue link for a failure.

| | |
|---|---|
| Commit (`git rev-parse --short HEAD`) | |
| Image tag deployed | |
| Cluster | ours / rehearsal |
| Cluster started at / stopped at | / |
| Public IP | |

## 1. Static

| ID | Result | Evidence |
|---|---|---|
| static-1 lint | | |
| static-2 render + kubeconform | | resources valid: |
| static-3 required values | | |
| static-4 all-digit tag | | |
| static-5 requests/limits | | |
| static-6 Terraform | | |
| static-7 no secret in repo | | |
| static-8 images build and run | | |
| static-9 PR checks | | PR #: |

## 2. Deploy

| ID | Result | Evidence |
|---|---|---|
| deploy-1 missing inputs | | |
| deploy-2 from scratch | | duration: |
| deploy-3 objects healthy | | HPA target: , LB services: |
| deploy-4 URLs answer | | |
| deploy-5 schema | | |
| deploy-6 password handling | | |
| deploy-7 idempotence | | pods restarted: |
| deploy-8 schema hook on upgrade | | |
| deploy-9 auto rollback | | errors during wait: |
| deploy-10 password change | OBSERVED | |

## 3. Functional

| ID | Result | Evidence |
|---|---|---|
| func-1 first vote | | seconds until shown: |
| func-2 change vote | | |
| func-3 several visitors | | total before / after: |
| func-4 load balancing | | pod names seen: |
| func-5 sticky sessions | | 400s with cookies blocked: /5 |
| func-6 Redis down | | poll restarts: , time back: |
| func-7 worker away | | |
| func-8 config change | | |

## 4. Resilience

| ID | Result | Evidence |
|---|---|---|
| res-1 baseline | | requests: , p95: |
| res-2 poll rollout | | errors: , duration: |
| res-3 result / worker rollout | | errors: , T+5 reached: |
| res-4 negative control | | errors with settings removed: |
| res-5 pod kill | | graceful errors: , forced errors: |
| res-6 node drain | | drain duration: , outage first/last FAIL: |
| res-7 database kill | | recovery time: |
| res-8 autoscaling | | peak replicas: , up in: , down in: |
| res-9 quota | | |

## 5. Data

| ID | Result | Evidence |
|---|---|---|
| data-1 pod restart | | |
| data-2 uninstall/reinstall | | |
| data-3 backup upload | | blob: |
| data-4 restore drill | | recovery time: |
| data-5 expiry rule | | |
| data-6 disks | | data disks: |

## 6. Operations

| ID | Result | Evidence |
|---|---|---|
| ops-1 rollback | | errors: |
| ops-2 history limit | | |
| ops-3 limitrange / quota | | |
| ops-4 CI deploy | | run: |
| ops-5 destroy | | |
| ops-6 stop / start | | IP unchanged: |
| ops-7 rehearsal | | total time: |
| ops-8 cluster stopped | | |

## Issues opened

| Test | Issue |
|---|---|
| | |
