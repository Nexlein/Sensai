# StatefulSet

What a Kubernetes StatefulSet is, why it exists, how its pieces fit together, and how the chart uses it for PostgreSQL and Redis. The component specifics are in [postgres.md](postgres.md) and [redis.md](redis.md); this document is the common ground.

## What it is

Kubernetes has several **workload controllers**: objects that keep a number of pods running from a template.

| | Deployment | StatefulSet |
|---|---|---|
| For | stateless programs: poll, worker, result | programs that keep data on disk: PostgreSQL, Redis |
| Pod names | random: `poll-7d9c6b5f4-x2k8p` | numbered, stable: `postgres-0` |
| Storage | none by itself (a PVC can be mounted, but all replicas share the same one) | **one PVC per pod**, created from a template and bound to that pod's name |
| After a pod is deleted | a new pod with a new name, started anywhere | **the same name** comes back and mounts **the same disk** |
| Replacing a pod | starts the new one **before** stopping the old one (rolling update) | stops the old one **before** creating the new one |
| Several replicas | interchangeable | numbered `-0`, `-1`, ... started and stopped in order, each with its own identity |
| Network identity | none: clients use a Service | each pod has its own DNS name through a headless Service |

A Deployment treats pods as **cattle**: any pod can be replaced by any other. A StatefulSet treats them as **pets**: `postgres-0` is a specific server with specific data, and Kubernetes keeps that identity.

## The four guarantees

1. **Stable name.** Pods are `<statefulset>-<ordinal>`: `postgres-0`, then `-1`, `-2` if there were more.
2. **Stable storage.** `volumeClaimTemplates` creates one PersistentVolumeClaim per pod, named `<template>-<pod>` (`data-postgres-0`). When the pod is recreated it mounts that same claim, so it finds its data.
3. **Stable DNS.** With a headless Service, the pod is reachable at `<pod>.<service>.<namespace>.svc` (`postgres-0.postgres-headless.bernstein.svc`), a name that survives restarts, unlike the pod's IP.
4. **Ordered, one at a time.** By default pods are created in order (`-0` must be Ready before `-1`), deleted in reverse, and a pod is **stopped before its replacement is created**. The StatefulSet never runs two pods with the same identity.

## Why the guarantees matter for a database

A Deployment with a PersistentVolumeClaim also runs one PostgreSQL pod, but its rolling update **starts the new pod before stopping the old one** (with one replica, the default `maxSurge` rounds up to 1 and `maxUnavailable` down to 0). Two pods then want the same disk:

- on another node, the new pod hangs: an Azure disk attaches to one node at a time (`Multi-Attach error`);
- on the same node, both can mount it, because `ReadWriteOnce` means one **node**, not one pod: two PostgreSQL servers start on one data directory, which corrupts it.

A StatefulSet cannot do that: it stops `postgres-0`, waits until it is gone, then creates the replacement, which mounts the same `data-postgres-0`. The cost is a few seconds without a server during every restart, which a single-instance database has anyway.

The same holds for Redis, whose append-only file lives on its disk.

## How the pieces fit together

```text
 StatefulSet "postgres"                     headless Service "postgres-headless"
   serviceName: postgres-headless  ───────►   clusterIP: None
   replicas: 1                                gives DNS names to the pods:
   template  ──► pod "postgres-0"               postgres-0.postgres-headless.<ns>.svc
   volumeClaimTemplates: [data]
        │
        └──► PVC "data-postgres-0" ──► PV (Azure disk) ──► mounted by "postgres-0"

 Service "postgres" (ClusterIP)  ──selects──►  pod "postgres-0"      ← what clients use
```

- **The StatefulSet** holds the pod template (like a Deployment) and the volume templates.
- **The headless Service** (`clusterIP: None`) has no virtual IP: its DNS name resolves to the pods themselves, and each pod gets its own record. The StatefulSet requires one, named in `serviceName`.
- **The PVC** is created by the StatefulSet the first time the pod is created, and **not deleted** when the pod or the StatefulSet goes away (see [Lifecycle](#lifecycle)).
- **The normal Service** (`postgres`, `redis`) is what clients use: a stable virtual IP that forwards to the pod while it is Ready. The apps never use the pod names.

The two Services select the same pod with the same labels.

## Setting one up from scratch

A minimal StatefulSet, stripped of what the chart adds:

```yaml
apiVersion: v1
kind: Service                      # 1. the headless Service
metadata:
  name: db-headless
spec:
  clusterIP: None
  selector: {app: db}
  ports: [{port: 5432}]
---
apiVersion: apps/v1
kind: StatefulSet                  # 2. the StatefulSet
metadata:
  name: db
spec:
  serviceName: db-headless         #    must name the Service above
  replicas: 1
  selector:
    matchLabels: {app: db}         #    must match the pod labels
  template:
    metadata:
      labels: {app: db}
    spec:
      containers:
        - name: db
          image: postgres:18
          volumeMounts:
            - name: data           #    must match the volume template's name
              mountPath: /var/lib/postgresql
  volumeClaimTemplates:            # 3. one PVC per pod: data-db-0
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 5Gi
```

Three things to get right: `serviceName` points to an existing headless Service, `selector` matches the template's labels, and the volume template's `name` is the one mounted in the container.

## How the chart sets it up

Both StatefulSets are built the same way. Fields, with where each is explained:

| Field | PostgreSQL | Redis | Why |
|---|---|---|---|
| `serviceName` | `postgres-headless` | `redis-headless` | The governing headless Service ([postgres.md](postgres.md#services)). |
| `replicas` | `1` | `1` | More replicas would be independent servers, not copies: neither has replication configured ([ADR-0002](adr/0002-redis-single-instance.md) for Redis). |
| `persistentVolumeClaimRetentionPolicy` | `Retain` / `Retain` | `Retain` / `Retain` | The disk survives `helm uninstall` and scaling to 0. Losing votes must be a deliberate step. |
| Pod `securityContext` | UID/GID 999, `fsGroup: 999` | UID/GID 999, `fsGroup: 999` | Non-root; `fsGroup` makes the fresh Azure disk (owned by root) writable. |
| Volume mount | `/var/lib/postgresql` | `/data` | Where each image expects its data ([PostgreSQL 18's moved](postgres.md#the-data-volume)). |
| `volumeClaimTemplates` | `data`, 5Gi, `managed-csi` | `data`, 1Gi, `managed-csi` | One ZRS Standard SSD each ([why ZRS](postgres.md#managed-csi-on-aks)). |
| Probes | `pg_isready` over TCP | `redis-cli ping` must answer `PONG` | See the traps below. |
| Pod annotation | none | `checksum/redis-secret` | Redis reads its password at start, so a new password must roll the pod. PostgreSQL ignores the variable after `initdb` ([postgres.md](postgres.md#probes)). |

Rendered, the shared skeleton looks like this (`helm template`, abbreviated):

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
spec:
  serviceName: redis-headless
  replicas: 1
  persistentVolumeClaimRetentionPolicy:
    whenDeleted: Retain
    whenScaled: Retain
  template:
    spec:
      containers:
        - name: redis
          volumeMounts:
            - name: data
              mountPath: /data
  volumeClaimTemplates:
    - metadata:
        name: data
        labels:                    # selector labels only, see below
          app.kubernetes.io/name: bernstein
          app.kubernetes.io/instance: bernstein
          app.kubernetes.io/component: redis
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: managed-csi
        resources:
          requests:
            storage: 1Gi
```

On the local cluster, after `helm install`, the StatefulSets created these pods and claims:

```text
NAME             READY   STATUS    RESTARTS   AGE
pod/postgres-0   1/1     Running   0          20s
pod/redis-0      1/1     Running   0          20s

NAME                                    STATUS   VOLUME      CAPACITY   ACCESS MODES   STORAGECLASS
persistentvolumeclaim/data-postgres-0   Bound    pvc-8899…   5Gi        RWO            standard
persistentvolumeclaim/data-redis-0      Bound    pvc-fe4d…   1Gi        RWO            standard
```

(`standard` is kind's default class; on AKS it is `managed-csi`.) Inspect them on any cluster with:

```sh
kubectl -n bernstein get statefulset,pod,pvc
kubectl -n bernstein describe statefulset redis
kubectl -n bernstein get pvc data-redis-0 -o yaml
```

## Lifecycle

What happens to the pod and its data, and what to expect. Rows marked ✓ were checked on a local cluster; the others are documented Kubernetes behaviour that has not been tried on ours.

| Event | Pod | Data |
|---|---|---|
| `kubectl delete pod redis-0` ✓ | Recreated with the same name, after the old one is gone | Same PVC remounted: 3 queued votes before, 3 after |
| `helm upgrade` changing the pod template (image, probes, annotation) ✓ | Rolling update: old pod stopped, then new pod created | Kept |
| `helm upgrade` changing `volumeClaimTemplates` ✓ | Upgrade **fails** ([traps](#traps-we-hit)) | Unchanged |
| `helm uninstall` ✓ | Deleted | **Kept**: the PVC is not a Helm object, and the policy is `Retain` |
| Reinstall after an uninstall ✓ | Created again as `-0` | The old PVC is found and reused, with its old data (and its old PostgreSQL password) |
| `kubectl delete pvc data-redis-0` | — | **Deleted** with the Azure disk (`managed-csi` has `reclaimPolicy: Delete`); this also stops its billing |
| Node drain or AKS upgrade | Stopped on the old node, recreated on another | The ZRS disk attaches to a node in any zone |
| Node fails (not drained) | Stays `Terminating`/`Unknown` until the node returns or the pod is force-deleted | Untouched. Kubernetes will not start a second pod while it cannot be sure the first one stopped: that is the "at most one" guarantee at work, at the price of waiting |

## Traps we hit

- **`volumeClaimTemplates` is immutable.** After creation, changing it (here `--set redis.persistence.size=2Gi`) makes the upgrade fail, checked on a local cluster:

  ```text
  Error: UPGRADE FAILED: server-side apply failed for object bernstein/redis apps/v1, Kind=StatefulSet: StatefulSet.apps "redis" is invalid: spec: Forbidden: updates to statefulset spec for fields other than 'replicas', 'ordinals', 'template', 'updateStrategy', 'revisionHistoryLimit', 'persistentVolumeClaimRetentionPolicy' and 'minReadySeconds' are forbidden
  ```

  The template's labels must therefore never contain something that changes, such as the image tag from `bernstein.labels`: the next version bump would break every upgrade. The chart puts **selector labels only** there ([postgres.md](postgres.md#volume-template)). To change a size or class afterwards, edit the PVC directly ([postgres.md](postgres.md#changing-the-volume)).
- **`persistence.size` only applies at the first install** for the same reason: the PVC exists afterwards.
- **A reinstall keeps the old data and the old password.** PostgreSQL reads `POSTGRES_PASSWORD` only when initialising an empty data directory ([postgres.md](postgres.md#changing-the-password)).
- **The image decides where its data lives.** PostgreSQL 18 moved `PGDATA` to `/var/lib/postgresql/18/docker` and expects the volume one level up; mounting the old path does not work ([postgres.md](postgres.md#the-data-volume)).
- **Probes must prove the server can serve.** PostgreSQL's first start runs a temporary server on the Unix socket only, so `pg_isready` goes over TCP ([postgres.md](postgres.md#probes)). Redis answers `LOADING` with exit code 0 while it replays its file, so the probe requires `PONG` ([redis.md](redis.md#probes)).
- **Deleting the StatefulSet does not delete the disk.** Without the retention policy being explicit, a reader could assume otherwise; the PVC keeps billing (E2 for PostgreSQL, E1 for Redis, [cost.md](cost.md)) until deleted by hand.

## Rejected alternatives

| Option | Why rejected |
|---|---|
| Deployment + PVC | Rolling update runs the new pod before stopping the old one: `Multi-Attach error` on another node, or two servers on one data directory on the same node. Setting `strategy: Recreate` avoids it for one replica, but gives no stable name, no per-pod claim, and no path to more replicas. |
| Several replicas for PostgreSQL | A StatefulSet gives each pod its own disk, not replication: two PostgreSQL pods would be two unrelated databases. Replication needs an operator (CloudNativePG) or manual setup. |
| An operator (CloudNativePG for PostgreSQL) | Real failover and backups, but an operator and its CRDs to install on the evaluator's fresh cluster, and more to explain. The natural next step ([postgres.md](postgres.md#why-a-statefulset)). |
| Managed services (Azure Database for PostgreSQL, Azure Cache for Redis) | Billed even while the cluster is stopped, and outside the cluster the evaluator provides. |
| A bare Pod with a PVC | Nobody recreates it if the node dies. |
