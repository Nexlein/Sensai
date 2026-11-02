# PostgreSQL

What the chart deploys for PostgreSQL, and why. Passwords in general (Secrets, pod restarts, where a password ends up) are covered in [helm-chart.md](helm-chart.md#passwords).

## Role in the application

PostgreSQL stores the votes: the worker upserts each vote into the `votes` table, and result reads the tally from it every second. The application requires **PostgreSQL 18**, and the table must exist before worker and result can do anything (`poll-application/schema.sql`). Losing the database means losing every vote, so its data lives on a persistent disk.

## What the chart deploys

| Object | File | Issue |
|---|---|---|
| StatefulSet `postgres`: one PostgreSQL 18 pod, `postgres-0` | `templates/postgres/statefulset.yaml` | #15 |
| PersistentVolumeClaim `data-postgres-0`: its data disk, created by the StatefulSet | same file (`volumeClaimTemplates`) | #15 |
| Service `postgres`: stable address `postgres:5432` for worker and result | `templates/postgres/service.yaml` | #15 |
| Service `postgres-headless`: DNS identity of the StatefulSet's pod | `templates/postgres/service.yaml` | #15 |
| Secret `postgres-credentials`: password of `postgres.user` | `templates/postgres/secret.yaml` | #17 |
| ConfigMap `postgres-initdb`: `schema.sql` run by the image at the first start of the database | `templates/postgres/initdb-configmap.yaml` | #61 |
| ConfigMap `postgres-schema`: `schema.sql` as a file (hook, deleted after use) | `templates/postgres/schema-configmap.yaml` | #16 |
| Job `postgres-schema`: applies it before each upgrade (hook, deleted after success) | `templates/postgres/schema-job.yaml` | #16, #61 |
| `files/schema.sql`: copy of `poll-application/schema.sql` read by the ConfigMap | `files/schema.sql` | #16 |

## Values

```yaml
postgres:
  image:
    registry: docker.io
    repository: library/postgres
    tag: "18.6"
    digest: sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336
  database: votes
  user: bernstein
  password: ""
  existingSecret: ""
  persistence:
    storageClass: managed-csi
    size: 5Gi
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      memory: 512Mi
```

| Key | Meaning |
|---|---|
| `image.*` | Official image. The digest is the multi-architecture index of `18.6` (published 2026-10-07), so every node pulls exactly the same image; the tag is only a readable hint and the `app.kubernetes.io/version` label. |
| `database`, `user` | Created by the image on first start (`POSTGRES_DB`, `POSTGRES_USER`); worker and result use the same values. |
| `password`, `existingSecret` | See [Password](#password). |
| `persistence.storageClass` | StorageClass of the data disk; empty for the cluster's default. See [Storage](#storage). |
| `persistence.size` | Requested size. **Fixed at the first install** (see [Changing the volume](#changing-the-volume)). |
| `resources` | CPU and memory of the container. Starting values; #30 tunes every workload. |

To bump PostgreSQL, update both `tag` and `digest`. The digest of a tag is the `Docker-Content-Digest` header returned by the registry for its manifest index:

```sh
TOKEN=$(curl -fsS "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/postgres:pull" | jq -r .token)
curl -fsSI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
  https://registry-1.docker.io/v2/library/postgres/manifests/18.6 | grep -i docker-content-digest
```

## Why a StatefulSet

PostgreSQL keeps its data on a disk and must never run twice on the same one. A Deployment's rolling update starts the new pod **before** stopping the old one, so two servers would want the same disk (`Multi-Attach error` on another node, or two servers on one data directory on the same node). A StatefulSet stops `postgres-0` before creating its replacement, gives it a stable name, and remounts the same disk. What a StatefulSet is, how its pieces fit together and how the chart uses it for both PostgreSQL and Redis: [k8s-statefulset.md](k8s-statefulset.md).

Rejected alternatives (from #15):

| Option | Why rejected |
|---|---|
| CloudNativePG operator | Real high availability (replicas, failover, backups to Blob storage), but an operator and its CRDs to install on the evaluator's fresh cluster, and more to explain. The natural next step. |
| Azure Database for PostgreSQL Flexible Server | Managed backups and HA, but billed even while the cluster is stopped, and the evaluator's cluster would need network access to it. |

## `templates/postgres/statefulset.yaml`

### Identity and data retention

```yaml
spec:
  serviceName: postgres-headless
  replicas: 1
  selector:
    matchLabels:
      {{- include "bernstein.selectorLabels" (dict "context" $ "component" "postgres") | nindent 6 }}
  persistentVolumeClaimRetentionPolicy:
    whenDeleted: Retain
    whenScaled: Retain
```

- **`serviceName`**: the headless Service that gives the pod its DNS name (see [Services](#services)).
- **`replicas: 1`**: a single server. More replicas would be independent databases, not copies: replication needs an operator or manual setup.
- **`persistentVolumeClaimRetentionPolicy`**: what happens to `data-postgres-0` when the StatefulSet is deleted (`helm uninstall`) or scaled down. `Retain` is the Kubernetes default, written explicitly because losing the votes must always be a deliberate step.

### Running as the postgres user

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 999
  runAsGroup: 999
  fsGroup: 999
  fsGroupChangePolicy: OnRootMismatch
...
securityContext:            # container level
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
```

- The image's entrypoint normally starts as root, fixes the data directory's owner, then drops to the `postgres` user. Starting directly as that user (UID/GID 999 in the Debian image: `id` in the pod prints `uid=999(postgres) gid=999(postgres)`) removes root from the container entirely.
- **`fsGroup: 999`**: a fresh Azure disk belongs to root; Kubernetes gives it group 999 and group write permission when mounting it, so the non-root server can create its data directory.
- **`fsGroupChangePolicy: OnRootMismatch`**: change ownership only if the volume's root does not already have the right group, instead of walking every file on each start.
- No capability is needed by PostgreSQL. Further hardening (read-only root filesystem, seccomp) is #33.

### Environment

```yaml
env:
  - name: POSTGRES_DB
    value: {{ .Values.postgres.database | quote }}
  - name: POSTGRES_USER
    value: {{ .Values.postgres.user | quote }}
  - name: POSTGRES_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ include "bernstein.secretName" (dict "context" $ "component" "postgres") }}
        key: password
```

The image reads these three variables **only when it initialises an empty data directory**: it creates the user, sets its password and creates the database. Afterwards they are ignored (see [Changing the password](#changing-the-password)). The password comes from the Secret through `secretKeyRef`, never as a literal value.

### The data volume

```yaml
volumeMounts:
  - name: data
    mountPath: /var/lib/postgresql
```

**The PostgreSQL 18 images moved the data directory**: `PGDATA` is now `/var/lib/postgresql/18/docker`, and the volume is expected one level up, on `/var/lib/postgresql`. In the pod:

```text
$ echo $PGDATA
/var/lib/postgresql/18/docker
$ psql -Atc 'show data_directory'
/var/lib/postgresql/18/docker
```

- Mounting at the old location, `/var/lib/postgresql/data`, as most older examples do, does not work with the 18 images (#15 notes the container then refuses to start).
- With `PGDATA` in a subdirectory, the `lost+found` directory that ext4 creates at the root of every new Azure disk is no longer inside it. Older setups had to work around `initdb` refusing a non-empty directory.
- The version in the path means a future PostgreSQL 19 would use `/var/lib/postgresql/19/docker` on the same volume, next to the 18 data, which is what `pg_upgrade` needs.

### Probes

```yaml
startupProbe:
  exec:
    command: ["sh", "-c", "pg_isready -h 127.0.0.1 -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""]
  periodSeconds: 5
  failureThreshold: 60
readinessProbe:      # same command
  periodSeconds: 5
  timeoutSeconds: 5
  failureThreshold: 3
livenessProbe:       # same command
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 6
```

`pg_isready` asks the server whether it accepts connections, and exits with 0 if it does. It runs through `sh -c` because Kubernetes does not expand `$VARIABLES` in a probe's command; the shell does.

| Probe | Question | Effect of failing |
|---|---|---|
| startup | Has the server finished starting? Up to 60 × 5 s = 5 min for the first `initdb` or a crash recovery. | The other probes wait; after 5 min the container is restarted. |
| readiness | Does it accept connections now? | Removed from the `postgres` Service until it does: worker and result get no connection instead of a broken one. |
| liveness | Is it still alive? Tolerates 6 × 10 s = 1 min of failures, so a slow checkpoint does not kill it. | Container restarted. |

**Why `-h 127.0.0.1` (TCP):** on the first start, the image initialises the database with a **temporary server listening on the Unix socket only**, then stops it and starts the real one. Without `-h`, `pg_isready` uses the socket and would declare the pod ready during initialisation, just before the server goes away. The pod's first log shows both servers:

```text
[44] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"     ← temporary server
PostgreSQL init process complete; ready for start up.
[1] LOG:  listening on IPv4 address "0.0.0.0", port 5432                   ← real server
```

There is **no `checksum/postgres-secret` annotation** on this pod, unlike worker and result: PostgreSQL ignores `POSTGRES_PASSWORD` after initialisation, so restarting it on a password change would only cause downtime.

### Shutdown

On `SIGTERM`, PostgreSQL does a *smart* shutdown: it waits for every client to disconnect. Worker and result keep their connections open, so it would wait until Kubernetes kills it after 30 s, and the next start would need a crash recovery.

The official image declares `STOPSIGNAL SIGINT`, the signal for a *fast* shutdown (disconnect clients, checkpoint, stop), and the container runtime honours it. Deleting the pod logs:

```text
[1] LOG:  received fast shutdown request
[64] LOG:  checkpoint starting: shutdown immediate
[1] LOG:  database system is shut down
```

and the replacement starts with `database system was shut down at ...`, without recovery. No `preStop` hook is therefore needed.

### Node drain

There is no PodDisruptionBudget on PostgreSQL: with one pod, a budget would make every `kubectl drain` hang. A drain therefore interrupts the database briefly (eviction, ZRS disk reattached on another node, start on the existing data) while the dependent pods report NotReady or restart. Details, and the place for the measured time, in [helm-availability.md](helm-availability.md#redis-and-postgresql-no-pdb-on-purpose).

### Resources

```yaml
resources:
  requests: {cpu: 100m, memory: 512Mi}
  limits: {cpu: "1", memory: 512Mi}
```

The requests reserve room on a node so PostgreSQL is not squeezed out by other pods. The memory request equals the limit, so the memory is guaranteed and the pod is the last to be evicted when a node runs short (the pod is still **Burstable**, not Guaranteed, because the CPU request is lower than the CPU limit). The memory limit stops a runaway query from taking the whole node (the container is restarted instead). The CPU limit of one core keeps a heavy query from starving its neighbours on a 2-vCPU node. See [resources.md](resources.md) and [ADR-0006](adr/0006-cpu-limits.md).

### Volume template

```yaml
volumeClaimTemplates:
  - metadata:
      name: data
      labels:
        {{- include "bernstein.selectorLabels" (dict "context" $ "component" "postgres") | nindent 10 }}
    spec:
      accessModes: ["ReadWriteOnce"]
      {{- with .Values.postgres.persistence.storageClass }}
      storageClassName: {{ . }}
      {{- end }}
      resources:
        requests:
          storage: {{ .Values.postgres.persistence.size }}
```

- The StatefulSet creates one PVC from this template per pod, named `<template>-<pod>`: `data-postgres-0`.
- **`ReadWriteOnce`**: an Azure disk is attached to a single node.
- **`{{- with ... }}`**: writes `storageClassName` only when a class is set; without it, Kubernetes uses the cluster's default class.
- **Selector labels only, not `bernstein.labels`.** Kubernetes forbids changing `volumeClaimTemplates` once the StatefulSet exists (`updates to statefulset spec for fields other than ... are forbidden`). The full labels contain the image tag, so the next PostgreSQL bump would make every `helm upgrade` fail.

## Storage

### `managed-csi` on AKS

`managed-csi` is a StorageClass that AKS creates in every cluster. It provisions an **Azure Standard SSD**, and, since Kubernetes 1.29, a **zone-redundant (ZRS)** one when the cluster spans availability zones, as ours does (zones 1-3) ([AKS storage concepts](https://learn.microsoft.com/en-us/azure/aks/concepts-storage#storage-classes)). Check on a cluster with `kubectl get storageclass managed-csi -o yaml`.

**ZRS matters here.** Our two nodes sit in different zones. A locally redundant (LRS) disk can only attach to a node in its own zone: when that node is drained (patch upgrade, maintenance), `postgres-0` could not move to the other node and would stay `Pending` (`volume node affinity conflict`) until the node came back. A ZRS disk is replicated across zones and attaches to a node in any of them.

On a cluster that is not AKS, set `postgres.persistence.storageClass` to one of its classes, or to `""` for its default.

### Size and cost

Azure bills a disk at the next tier up: the 5 GiB requested are billed as an **E2 (8 GiB)** disk. Austria East prices, 2026-10-12, [Azure Retail Prices API](https://prices.azure.com/api/retail/prices):

| Disk | €/month | Operations |
|---|---|---|
| Standard SSD E2 ZRS (`managed-csi`, our cluster) | 0.792 | 0.0034 € per 10,000 |
| Standard SSD E2 LRS (`managed-csi`, single-zone cluster) | 0.528 | 0.0023 € per 10,000 |
| Premium SSD P2 ZRS (`managed-csi-premium`) | 1.916 | not billed |

Standard SSD bills disk operations, but only while the cluster runs. An idle PostgreSQL measured 6 write operations in 120 s (`pg_stat_io`), and votes add about one write each, so the total stays at a few cents. `managed-csi-premium` would only be cheaper above about 1.3 operations per second around the clock. The project's totals are in [cost.md](cost.md).

## Services

`templates/postgres/service.yaml` holds two Services selecting the same pod.

| Service | `clusterIP` | DNS name resolves to | Used by |
|---|---|---|---|
| `postgres` | a virtual IP | that virtual IP, which forwards to `postgres-0` while it is Ready | worker and result (`POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432`) |
| `postgres-headless` | `None` | the pod's own IP; `postgres-0.postgres-headless.<namespace>.svc` names the pod | the StatefulSet (`serviceName`) |

- A **headless** Service (`clusterIP: None`) has no virtual IP: DNS returns the pods directly. A StatefulSet needs one to give each pod a stable DNS name.
- Clients use the normal `postgres` Service: its address never changes, and the readiness probe keeps traffic away from a server that is not ready.
- The container port is named `postgres` and both Services target it by name (`targetPort: postgres`), so the number is written once.

## Schema

Worker and result need the `votes` table (`poll-application/schema.sql`). Without it the worker's upsert fails and it exits, and result's query fails and exits: both crash-loop. The evaluator deploys on an empty cluster, so the chart creates the table itself, in the right order, and can do it again at any time. Two mechanisms cover the two situations:

| Situation | Applied by | Why this one |
|---|---|---|
| First install (empty data volume) | the image's `/docker-entrypoint-initdb.d`, fed by the `postgres-initdb` ConfigMap | runs before PostgreSQL is Ready, so `helm install --wait` can succeed |
| Every upgrade (existing volume) | the `postgres-schema` Job, a `pre-upgrade` hook | initdb scripts never run on an existing volume; a changed schema must be in place before new pods start |

```sql
CREATE TABLE IF NOT EXISTS votes
(
  id text PRIMARY KEY,
  vote text NOT NULL
);
```

`IF NOT EXISTS` makes the statement **idempotent**: running it with the table already there does nothing and succeeds. That is what allows the chart to run it on every upgrade.

### `files/schema.sql`

Helm can only read files **inside the chart directory** (`.Files.Get` cannot reach `poll-application/`), and a symlink to the outside is not followed when the chart is packaged. The file is therefore a **copy**. The application's file remains the source of truth, so the two must stay identical:

```sh
diff poll-application/schema.sql charts/bernstein/files/schema.sql    # no output = in sync
```

This check is to be run in CI by #11.

The two hooks are explained in general, and listed with the chart's others, in [helm-hooks.md](helm-hooks.md).

### `templates/postgres/initdb-configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-initdb
data:
  schema.sql: |
    {{- .Files.Get "files/schema.sql" | trim | nindent 4 }}
```

A regular ConfigMap, mounted read-only on `/docker-entrypoint-initdb.d` in `templates/postgres/statefulset.yaml` (volume `initdb`). The official image runs every `*.sql` file of that directory once, while it initialises an empty data directory, against `POSTGRES_DB` and before it accepts connections from the network. The pod is therefore not Ready until the table exists.

**The trap that made it necessary (#61).** Until then the schema Job was `post-install,pre-upgrade`. Helm runs `post-install` hooks **after** it has waited for the release's objects, and `deploy.sh` uses `--wait`. result exits while `votes` does not exist, so it never became Ready, so the hook never ran:

```
Error: INSTALLATION FAILED: resource Deployment/bernstein/result not ready. status: InProgress, message: Available: 0/1
...
context deadline exceeded
```

`kubectl get job -n bernstein` was empty, and `kubectl logs deploy/result` showed `Error performing query: error: relation "votes" does not exist`. A following `helm upgrade` worked (the Job runs there *before* the objects), which hid the problem. With the ConfigMap, checked on a local cluster: `helm install --wait` on an empty cluster finishes in 24 s with no restart, and the next `helm upgrade --wait` leaves no Job or hook ConfigMap behind.

The file is not reapplied by editing the ConfigMap: the image reads it only on an empty volume. That is what the Job is for.

### `templates/postgres/schema-configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-schema
  annotations:
    "helm.sh/hook": pre-upgrade
    "helm.sh/hook-weight": "-5"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
data:
  schema.sql: |
    {{- .Files.Get "files/schema.sql" | trim | nindent 4 }}
```

- **`.Files.Get "files/schema.sql"`** returns the file's content as a string; **`trim`** removes its final newline and **`nindent 4`** starts a new line and indents every line by 4 spaces, as a block scalar (`|`) requires.
- **It is a hook as well**, with weight `-5` (lower runs first, the Job is `0`). On `helm upgrade`, regular objects are applied *after* the `pre-upgrade` hooks, so a normal ConfigMap would still contain the *previous* `schema.sql` when the Job runs: a changed schema would only be applied by the *next* upgrade.

### `templates/postgres/schema-job.yaml`

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-schema
  annotations:
    "helm.sh/hook": pre-upgrade
    "helm.sh/hook-weight": "0"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  backoffLimit: 6
  activeDeadlineSeconds: 600
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: schema
          image: {{ include "bernstein.image" (dict "context" $ "component" "postgres") }}
          env:
            - name: PGHOST
              value: postgres
            - name: PGDATABASE
              value: {{ .Values.postgres.database | quote }}
            - name: PGUSER
              value: {{ .Values.postgres.user | quote }}
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ include "bernstein.secretName" (dict "context" $ "component" "postgres") }}
                  key: password
          command:
            - sh
            - -ec
            - |
              until pg_isready -q; do
                echo "waiting for postgres"
                sleep 2
              done
              psql -v ON_ERROR_STOP=1 -f /schema/schema.sql
```

**Hook annotations**

- **`helm.sh/hook: pre-upgrade`**: Helm does not apply the object with the others; it runs it at this moment of the release. Before an upgrade, the database of the previous revision is still running, and the new schema is in place before the new application pods start. Not `post-install`: see [the trap above](#templatespostgresinitdb-configmapyaml); the first install is covered by initdb.
- **`hook-weight`**: hooks of the same event run in ascending order; Helm waits for a Job hook to complete before running the next one.
- **`hook-delete-policy: before-hook-creation,hook-succeeded`**: `hook-succeeded` deletes the Job and ConfigMap once the Job completed, so nothing is left behind; `before-hook-creation` deletes a leftover from a previous failed run before creating a new one, which a Job with a fixed name needs (otherwise: `jobs.batch "postgres-schema" already exists`). A **failed** Job is kept, for `kubectl logs job/postgres-schema`.

**Job settings**

- **`PGHOST=postgres`**: the Service, as worker and result will use. `psql` and `pg_isready` read the `PG*` variables themselves, so no connection string, and no password on a command line.
- **`PGPASSWORD`** comes from the same Secret as the server, through `bernstein.secretName`, so it also works with `postgres.existingSecret`.
- **`until pg_isready -q`**: on an upgrade the server is normally up, but it may be restarting (node drain, crash). Waiting in the script makes the Job independent of that.
- **`psql -v ON_ERROR_STOP=1 -f`**: by default `psql` keeps going after an SQL error and exits 0, so a broken schema would go unnoticed. With `ON_ERROR_STOP` it stops and exits non-zero, the Job fails, and so does `helm install/upgrade` (and `--atomic` rolls back).
- **`sh -ec`**: `-e` stops the script on the first failing command.
- **`backoffLimit: 6`** retries a failed pod up to 6 times (with growing delay); **`activeDeadlineSeconds: 600`** stops everything after 10 minutes if PostgreSQL never answers, instead of hanging the release.
- **`restartPolicy: Never`**: each retry is a new pod, so the logs of the failed attempts stay readable.
- **Same image as the server** (`bernstein.image` for the `postgres` component): `psql` and `pg_isready` are already in it, and the client version matches the server's. It runs as UID 999 without privileges, like the server (see [Running as the postgres user](#running-as-the-postgres-user)).

### Rejected alternatives (from #16)

| Option | Why rejected |
|---|---|
| Mount `schema.sql` in `/docker-entrypoint-initdb.d` **alone** | The image only runs those files when the data directory is **empty**: nothing happens on an existing volume (an upgrade, or a reinstall that keeps the disk), and a changed schema is never applied. Used since #61 **together with** the Job, for the first install only. |
| `pre-install` hook Job | Needs the Secret, the Service and the StatefulSet, which do not exist yet; making them hooks would take them out of the release (not upgraded, not removed). |
| Install without `--wait` | The Job would run, but a real failure (bad image, missing Secret) would no longer fail the install nor trigger the automatic rollback. |
| initContainer in worker and result | Runs once per replica, concurrently, and gives the applications the job of managing the schema (and the database credentials to do it). |
| Regular (non-hook) Job | Created with everything else, so it may start before PostgreSQL exists, and a Job's `spec.template` cannot be changed on upgrade (`field is immutable`). |

The issue also suggested a `hook-weight` placing the Job "after the Secret". The Secret is a regular object, not a hook, and the Job only runs on upgrade, when the previous revision's Secret is in place.

## Keeping and deleting the data

| Action | Data |
|---|---|
| `kubectl delete pod postgres-0`, node drain, `helm upgrade` | Kept: the new pod mounts the same disk. |
| `helm uninstall` | Kept: the PVC is not a Helm object and the retention policy is `Retain`. |
| Reinstall after an uninstall | Reused: the data directory exists, so `initdb` is skipped. The **old password** stays valid, whatever `postgres.password` now says. |
| `kubectl -n bernstein delete pvc data-postgres-0` | **Deleted**, with the Azure disk (`managed-csi` has `reclaimPolicy: Delete`). Also stops its billing. |

### Changing the volume

`persistence.size` and `persistence.storageClass` only apply when the PVC is created. To grow the disk later, edit the PVC itself (`managed-csi` allows expansion), then align the value so a reinstall asks for the same size:

```sh
kubectl -n bernstein patch pvc data-postgres-0 -p '{"spec":{"resources":{"requests":{"storage":"10Gi"}}}}'
```

Changing the template of the existing StatefulSet makes `helm upgrade` fail (see [Volume template](#volume-template)): it needs `kubectl -n bernstein delete statefulset postgres --cascade=orphan` (the pod and its disk stay), then the upgrade recreates the StatefulSet.

## Backups

A persistent volume survives pod restarts, not a lost disk, a bad `DROP TABLE`, or `kubectl delete pvc`. The CronJob `postgres-backup` keeps copies outside the cluster. Off by default (`postgres.backup.enabled: false`): it needs the storage account and identity from Terraform ([terraform.md](terraform.md#backup-storage-and-identity)).

### Values

```yaml
postgres:
  backup:
    enabled: false
    schedule: "0 */6 * * *"
    storageAccount: ""          # terraform output backup_storage_account
    container: postgres-backups # terraform output backup_container
    clientId: ""                # terraform output backup_client_id
    uploadImage: { registry: mcr.microsoft.com, repository: azure-cli, tag: "2.91.0", digest: sha256:933e... }
    sizeLimit: 1Gi
```

Enable it through `make deploy` by exporting `BACKUP_STORAGE_ACCOUNT`, `BACKUP_CONTAINER` and `BACKUP_CLIENT_ID` (the three Terraform outputs, [deploy.md](deploy.md#use)); CI sets them from repository variables ([ci-deploy.md](ci-deploy.md)). A hand-written `helm upgrade --set postgres.backup.enabled=true ...` works too, but the next `make deploy` removes the CronJob again, since the script does not use `--reuse-values`. With `enabled` and no `storageAccount` or `clientId`, `helm template` fails with `values: postgres.backup.storageAccount is required when postgres.backup.enabled`.

### `templates/postgres/backup-serviceaccount.yaml`

A ServiceAccount `postgres-backup` annotated `azure.workload.identity/client-id: <clientId>`. Its name and the release namespace must match the subject of the federated credential in Terraform (`system:serviceaccount:bernstein:postgres-backup`); change one, change the other (`backup_namespace`, `backup_service_account`).

### `templates/postgres/backup-cronjob.yaml`

One pod, two steps sharing an `emptyDir`:

1. **initContainer `dump`**, the `postgres` image already used by the StatefulSet: `pg_dump -Fc -f /backup/dump.pgdump`, with `PGHOST=postgres` and the password from the same Secret. Using the server's own image guarantees a `pg_dump` of the right major version. `-Fc` is the custom format: compressed, and restorable table by table with `pg_restore`.
2. **container `upload`**, `mcr.microsoft.com/azure-cli`: `az login --service-principal --federated-token "$(cat $AZURE_FEDERATED_TOKEN_FILE)"` then `az storage blob upload --auth-mode login`, blob name `<UTC timestamp>.pgdump`.

The pod label `azure.workload.identity/use: "true"` makes AKS's workload identity webhook inject `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_FEDERATED_TOKEN_FILE` and a projected token. No secret is involved; the storage account has shared keys disabled.

Settings that matter:

| Field | Why |
|---|---|
| `concurrencyPolicy: Forbid` | A slow dump never overlaps the next. |
| `startingDeadlineSeconds: 600` | After a cluster stop (`make cluster-stop`), missed slots are skipped instead of all running at once. |
| `backoffLimit: 2`, `activeDeadlineSeconds: 1800` | A failing run retries twice and never hangs forever. |
| `successfulJobsHistoryLimit: 3` | Keeps the last logs. |
| `AZURE_CONFIG_DIR=/tmp/azure` (emptyDir) | The CLI writes its login state there; the image's home directory is not writable as uid 999. |

The two-container design (A) was chosen over a custom image with `pg_dump` and `az`: no image to build, scan and keep in CI, both images official and digest-pinned.

### Retention

Not done by the CronJob: a Blob lifecycle rule in Terraform deletes dumps 7 days after upload. Also nothing can fail halfway and leave the cluster in charge of deleting data.

### Restore

Procedure in [runbooks/restore.md](runbooks/restore.md).

### Rejected alternatives

- **Azure Disk snapshots (VolumeSnapshot + CSI)**: crash-consistent only, tied to the zone and subscription.
- **CloudNativePG built-in backups**: would need the operator and its CRDs on the evaluator's fresh cluster.
- **Storage account key or SAS token in a Secret**: a secret to rotate and leak; workload identity needs none.

## Password

The subject forbids `POSTGRES_PASSWORD` in the repository, and requires documenting how and where to set it. It is **provided by the operator at deploy time**, never generated by the chart: the evaluator must be able to choose it, and a password regenerated on an upgrade would no longer match the one stored in the database.

### Providing it

```sh
export POSTGRES_PASSWORD="$(openssl rand -base64 32)"   # or any long password you choose
helm upgrade --install bernstein charts/bernstein -n bernstein ... \
  --set-string postgres.password="$POSTGRES_PASSWORD"
```

- The value comes from an environment variable: it is never written to a file, and the shell history only contains `$POSTGRES_PASSWORD`.
- `--set-string` keeps it a string even if it looks like a number.
- Use a long random password: the checksum annotation exposes a hash of it (see [helm-chart.md](helm-chart.md#where-a-password-ends-up)).

### Bringing your own Secret

When the password is managed outside Helm, create the Secret first and point the chart to it:

```sh
kubectl -n bernstein create secret generic pg-auth --from-literal=password="$POSTGRES_PASSWORD"
helm upgrade --install bernstein charts/bernstein -n bernstein ... --set postgres.existingSecret=pg-auth
```

The Secret must have a `password` key. Its name is checked by the schema (lowercase letters, digits, `-` and `.`, at most 253 characters, as Kubernetes requires).

### `templates/postgres/secret.yaml`

```yaml
{{- if not .Values.postgres.existingSecret }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "bernstein.secretName" (dict "context" $ "component" "postgres") }}
  labels:
    {{- include "bernstein.labels" (dict "context" $ "component" "postgres") | nindent 4 }}
type: Opaque
data:
  password: {{ required `postgres.password is required: pass --set-string postgres.password="$POSTGRES_PASSWORD", or set postgres.existingSecret` .Values.postgres.password | b64enc | quote }}
{{- end }}
```

- **`{{- if not .Values.postgres.existingSecret }}` … `{{- end }}`**: with an existing Secret, the whole file renders to nothing, so the chart creates no Secret.
- **`name`**: `bernstein.secretName` returns `postgres-credentials` here. Pods use the same helper to find the Secret, so the name is written once ([helm-helpers.md](helm-helpers.md#bernsteinsecretname)).
- **`type: Opaque`**: the generic Secret type, for arbitrary key/value data.
- **`required "message" .Values.postgres.password`**: with no password, Helm stops before touching the cluster:

  ```text
  Error: INSTALLATION FAILED: execution error at (bernstein/templates/postgres/secret.yaml:10:15): postgres.password is required: pass --set-string postgres.password="$POSTGRES_PASSWORD", or set postgres.existingSecret
  ```

- **The message is between backticks**: in Go templates, `` `...` `` is a raw string, so the `"` inside need no escaping.
- **`| b64enc`**: values under a Secret's `data` must be base64-encoded. **`| quote`** keeps the result a YAML string.

**Why the check is in the template and not in the schema:** "`password` or `existingSecret`" needs a JSON Schema `anyOf`, whose error (`'anyOf' failed` followed by one line per branch) does not say what to do. `required` prints a message that gives the exact command.

### Changing the password

PostgreSQL only reads `POSTGRES_PASSWORD` when it **initialises an empty data directory**. Changing it later and upgrading gives worker and result the new password (their checksum annotation changes, so they restart), but the database still expects the old one: reinstalling over the kept disk with a new password, a client using the new one gets `FATAL:  password authentication failed for user "bernstein"`. Change it inside PostgreSQL as well:

```sql
ALTER USER bernstein PASSWORD '<new password>';
```

The full rotation procedure (order of the steps, avoiding downtime) is documented with the deployment guide (#36).

## Verifying

Without a cluster:

```sh
OK="--set global.registry=example.azurecr.io --set-string global.tag=dev --set-string postgres.password=s3cret"

# Secret with the given password, decoded back
helm template bernstein charts/bernstein $OK -s templates/postgres/secret.yaml \
  | awk '/password:/ {print $2}' | tr -d '"' | base64 -d

# Fails with the "postgres.password is required" message
helm template bernstein charts/bernstein --set global.registry=x.io --set-string global.tag=dev

# Manifests valid against the Kubernetes 1.36 API
helm template bernstein charts/bernstein $OK | nix shell nixpkgs#kubeconform -c kubeconform -strict -summary -kubernetes-version 1.36.0
```

`helm template ... --set postgres.existingSecret=pg-auth -s templates/postgres/secret.yaml` fails with `could not find template templates/postgres/secret.yaml in chart`: `-s` refuses a template that renders to nothing, which is the expected result.

On a local cluster ([how](helm-chart.md#testing-on-a-local-cluster)), checked on 2026-10-12 with Kubernetes 1.36.1:

| Check | Command | Result |
|---|---|---|
| Starts | `kubectl -n bernstein wait --for=condition=Ready pod/postgres-0` | Ready in 15 s, image pull included |
| Non-root | `kubectl -n bernstein exec postgres-0 -- id` | `uid=999(postgres) gid=999(postgres)` |
| Data on the volume | `kubectl -n bernstein exec postgres-0 -- psql -U bernstein -d votes -Atc 'show data_directory'` | `/var/lib/postgresql/18/docker` |
| Password through the Service | `kubectl -n bernstein run psql --rm -i --restart=Never --image=<postgres image> --env PGPASSWORD=<password> -- psql -h postgres -U bernstein -d votes -c 'select 1'` | works; a wrong password gets `password authentication failed` |
| Survives a pod deletion | insert a row, `kubectl -n bernstein delete pod postgres-0`, select it again | row kept, fast shutdown, no recovery |
| Schema on a fresh install | `kubectl -n bernstein exec postgres-0 -- psql -U bernstein -d votes -c '\d votes'` after `helm install --wait` | table present; Job and ConfigMap already deleted |
| Upgrade with the table present | insert a row, `helm upgrade`, select it | revision 2 deployed, row kept |
| Table dropped, then upgrade | `DROP TABLE votes`, `helm upgrade`, `\dt` | table recreated (revision 3) |
| Survives `helm uninstall` | `kubectl -n bernstein get pvc` after uninstalling | `data-postgres-0` still `Bound`; a reinstall finds the row |

The `fsGroup` ownership can only be checked on AKS: the local cluster's volumes are plain world-writable directories.
