  # Helm hooks

What a Helm hook is, how Helm runs it, and the list of hooks in `charts/bernstein`, in the order they run. For an overview of every file in the chart, see [helm-chart.md](helm-chart.md).

## What a hook is

A **hook** is a Kubernetes object that Helm creates at a chosen moment of a release's life, instead of applying it together with the other manifests. One annotation turns an ordinary object into a hook:

```yaml
metadata:
  annotations:
    "helm.sh/hook": post-install,pre-upgrade
```

| | Normal object | Hook |
|---|---|---|
| Applied | all together, in one batch | at the moment named in `helm.sh/hook` |
| Waited for | only with `--wait` (until Pods are Ready) | always, for a Job or a Pod: until it completes |
| Part of the release | yes: tracked, upgraded, removed by `helm uninstall` | no: Helm creates it and, unless a delete policy says otherwise, forgets it |
| If it fails | the release is `failed` only with `--wait` | the install/upgrade **fails** |

The last row is the reason to use one. "Create the table, and only go on if that worked" cannot be expressed with normal objects, which Helm applies without any order or success check.

## The moments

```text
helm install                                  helm upgrade
────────────                                  ────────────
pre-install hooks                             pre-upgrade hooks
create the objects (+ --wait)                 apply the new objects (+ --wait)
post-install hooks                            post-upgrade hooks
```

| Hook | Runs |
|---|---|
| `pre-install` / `post-install` | before any object is created / after all of them are |
| `pre-upgrade` / `post-upgrade` | before the new revision is applied / after it is |
| `pre-delete` / `post-delete` | around `helm uninstall` |
| `pre-rollback` / `post-rollback` | around `helm rollback` |
| `test` | only on `helm test` |

Several moments are separated by a comma. `post-install,pre-upgrade` means "after the first install, and before every later upgrade". Our schema Job used it until #61 and now runs `pre-upgrade` only, because a `post-install` hook does not run under `--wait` when the release cannot become Ready without it (see [below](#the-hooks-of-the-chart)).

A hook does not run when its moment does not happen: on a first `helm install` the `pre-upgrade` hooks are skipped, and on `helm upgrade` the `post-install` ones are.

## Annotations

### `helm.sh/hook-weight`

Hooks of the same moment run in **ascending weight** (a string holding an integer, negative allowed; default `"0"`). For a Job or Pod hook, Helm waits for completion before starting the next one. Equal weights are sorted by kind, then name, so rely on weights, not on that.

### `helm.sh/hook-delete-policy`

When Helm deletes the hook object. A comma-separated list:

| Policy | Deletes the object |
|---|---|
| `before-hook-creation` | before creating it again on the next run (the default if no policy is set) |
| `hook-succeeded` | once it completed successfully |
| `hook-failed` | once it failed |

Without `before-hook-creation`, a second run fails with `jobs.batch "postgres-schema" already exists`, because the hook is named and Helm does not own it. Without `hook-succeeded`, the finished object stays in the cluster for good, outside of the release: `helm uninstall` does not remove it. We keep **failed** hooks on purpose (no `hook-failed`): `kubectl logs job/postgres-schema` is how a broken schema is diagnosed.

## What Helm does with a hook

- **`helm template`** prints hooks along with the other manifests, annotations included. `--no-hooks` leaves them out (the Job count of our chart goes from 1 to 0).
- **`helm install` / `upgrade`** create them at their moment and wait for the Job to finish. A failed Job (or `activeDeadlineSeconds` exceeded) fails the command; with `--atomic` the upgrade is rolled back.
- **`helm rollback`** does not run `pre/post-upgrade` hooks; it only runs the `*-rollback` ones.
- **`helm uninstall`** removes the release's objects, and the hooks only if a delete policy applies.

## The hooks of the chart

Listed in the order Helm runs them: first by moment, then by weight. Both run before an upgrade only. The first install gets its schema from PostgreSQL's own initialisation instead ([postgres.md](postgres.md#templatespostgresinitdb-configmapyaml)): they used to be `post-install` too, and **a `post-install` hook never runs when `--wait` is used and a Deployment cannot become Ready without what the hook creates** (#61).

| Order | Moment | Weight | Object | File | Issue |
|---|---|---|---|---|---|
| 1 | `pre-upgrade` | `-5` | ConfigMap `postgres-schema` | `templates/postgres/schema-configmap.yaml` | #16, #61 |
| 2 | `pre-upgrade` | `0` | Job `postgres-schema` | `templates/postgres/schema-job.yaml` | #16, #61 |

Rendered by `helm template`:

```text
# Source: bernstein/templates/postgres/schema-configmap.yaml
kind: ConfigMap
  name: postgres-schema
    "helm.sh/hook": pre-upgrade
    "helm.sh/hook-weight": "-5"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
# Source: bernstein/templates/postgres/schema-job.yaml
kind: Job
  name: postgres-schema
    "helm.sh/hook": pre-upgrade
    "helm.sh/hook-weight": "0"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
```

### Timeline of a first install

```text
helm install --wait
  1. Secret, ConfigMap postgres-initdb, StatefulSet postgres, Services,
     Deployments, ...                                                (normal objects)
  2. postgres-0 starts on an empty volume: the image runs schema.sql from
     /docker-entrypoint-initdb.d, then the pod becomes Ready
  3. result, worker, poll find the table and become Ready
  4. Helm's wait ends → release "deployed"             (no hook involved)
```

Before #61 steps 2 and 3 were a `post-install` Job that Helm only started after step 3 had succeeded, which it could not without the table: `context deadline exceeded` after the timeout ([postgres.md](postgres.md#templatespostgresinitdb-configmapyaml)).

### Timeline of an upgrade

```text
helm upgrade
  1. [pre-upgrade, weight -5]   ConfigMap postgres-schema created    ← the NEW schema.sql
  2. [pre-upgrade, weight  0]   Job postgres-schema runs and completes
  3. the new revision's objects are applied (new worker/result pods, ...)
  4. release revision N+1 "deployed"
```

### Why these moments and weights

- **No `post-install` and no `pre-install`**: `post-install` hooks run after Helm's `--wait`, which cannot finish here (result needs the table); `pre-install` runs before the Secret, the Service and the StatefulSet exist. The first install uses PostgreSQL's initdb directory instead.
- **`pre-upgrade`, not `post-upgrade`**: the table must exist before the *new* application pods start. After the upgrade, a new worker could already be crash-looping on a missing table. The old PostgreSQL pod is still running at this point, so the Job has something to talk to.
- **Weight `-5` for the ConfigMap**: it must exist when the Job's pod mounts it. It is a hook too because regular objects are applied *after* the `pre-upgrade` hooks, so a plain ConfigMap would still hold the previous `schema.sql` while the Job runs, and a changed schema would only be applied one upgrade late. Only the gap between `-5` and `0` matters, not the values.
- **The Secret is not a hook** and needs no weight: the hooks only run on upgrade, when the previous revision's is in place. (The issue asked for a weight "after the Secret"; there is nothing to order against.)
- **`before-hook-creation,hook-succeeded` on both**: the success path leaves nothing behind (the ConfigMap is deleted after the Job completes, not before: checked on a local cluster, `kubectl get jobs,cm` is empty after each run), and a leftover from a failed run does not block the next one.

Details of the Job itself (`ON_ERROR_STOP`, retries, why the same image as the server) are in [postgres.md](postgres.md#schema).

## Adding a hook

1. Put the object in `templates/<component>/` like any other, with the labels helpers.
2. Add the three annotations. Pick the moment from what the hook needs to exist (what is created before/after), not from convenience.
3. Choose a weight only if it depends on another hook, and a delete policy: `before-hook-creation,hook-succeeded` unless you want to inspect the finished object.
4. Add a row to the table above, **in run order**, and describe the hook in its component's document.
5. Test it on a local cluster for both moments ([how](helm-chart.md#testing-on-a-local-cluster)): `helm install`, then `helm upgrade`, and check what `kubectl get jobs,cm` leaves behind.

## Rejected alternatives

| Option | Why rejected |
|---|---|
| A normal Job | Created with everything else, so possibly before PostgreSQL exists; a Job's pod template is immutable, so the next `helm upgrade` fails with `field is immutable`. |
| An initContainer in the applications | Runs in every replica, concurrently, and gives the applications the job of managing the schema. |
| A step in `scripts/deploy.sh` (#23) | Not run by an evaluator who uses `helm upgrade --install` directly, and not covered by `--atomic`. A hook belongs to the release. |
