# Redis

What the chart deploys for Redis, and why. Passwords in general (Secrets, pod restarts, where a password ends up) are covered in [helm-chart.md](helm-chart.md#passwords).

## Role in the application

Redis is the buffer between poll and the worker: poll pushes each vote onto the list `votes` (`RPUSH`), the worker pops them (`BLPOP`). Votes waiting in the list are lost if Redis restarts without persistence, and anyone able to reach an unprotected Redis can read or delete them. The application requires **Redis 8.x**, supports a password (`REDIS_PASSWORD`, Redis `requirepass`), and the worker hardcodes port **6379**.

## What the chart deploys

| Object | File | Issue |
|---|---|---|
| Secret `redis-credentials`: the Redis password | `templates/redis/secret.yaml` | #17 |
| StatefulSet `redis`: one Redis 8 pod, `redis-0` | `templates/redis/statefulset.yaml` | #18 |
| PersistentVolumeClaim `data-redis-0`: its data disk, created by the StatefulSet | same file (`volumeClaimTemplates`) | #18 |
| Service `redis`: stable address `redis:6379` for poll and worker | `templates/redis/service.yaml` | #18 |
| Service `redis-headless`: DNS identity of the StatefulSet's pod | `templates/redis/service.yaml` | #18 |

## Values

```yaml
redis:
  image:
    registry: docker.io
    repository: library/redis
    tag: "8.10.2"
    digest: sha256:2c2dff791878316e3b083188be0d578423b24813cdda5de0e80ea4f7b3e6bfd6
  existingSecret: ""
  maxmemory: 192mb
  persistence:
    storageClass: managed-csi
    size: 1Gi
  resources:
    requests:
      cpu: 50m
      memory: 128Mi
    limits:
      cpu: 500m
      memory: 256Mi
```

| Key | Meaning |
|---|---|
| `image.*` | Official image. The digest is the multi-architecture index of `8.10.2` (queried 2026-10-13; it is also what the `8` tag pointed to), so every node pulls exactly the same image. The tag is only a readable hint and the `app.kubernetes.io/version` label. |
| `existingSecret` | Name of a Secret created beforehand, with a `password` key. Empty: the chart generates the password. See [Password](#password). |
| `maxmemory` | Memory Redis may use for data. See [Memory and CPU](#memory-and-cpu). |
| `persistence.storageClass` | StorageClass of the data disk; empty for the cluster's default. Same reasoning as [PostgreSQL's](postgres.md#storage). |
| `persistence.size` | Requested size. **Fixed at the first install** (see [Changing the volume](postgres.md#changing-the-volume), same rules). |
| `resources` | CPU and memory of the container. #30 reviews the requests and limits of every workload. |

There is **no `redis.password` value**, unlike PostgreSQL: no human needs to know this password, only Redis, poll and the worker, which all read it from the same Secret.

To bump Redis, update both `tag` and `digest`. The digest of a tag is the `Docker-Content-Digest` header returned by the registry for its manifest index:

```sh
TOKEN=$(curl -fsS "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/redis:pull" | jq -r .token)
curl -fsSI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" \
  https://registry-1.docker.io/v2/library/redis/manifests/8.10.2 | grep -i docker-content-digest
```

## Why one StatefulSet pod, not Sentinel or a Cluster

Redis here is a queue between two components, not a database: votes live in it for a fraction of a second, until the worker pops them. The design is **one pod with a disk**, and the reasoning is recorded in [ADR-0002](adr/0002-redis-single-instance.md).

- **Why a StatefulSet** and not a Deployment: a Deployment's rolling update starts the new pod before stopping the old one, so two Redis servers would want the same disk. What a StatefulSet is and how the chart uses it: [k8s-statefulset.md](k8s-statefulset.md).
- **While Redis is down**, poll's `/readyz` fails (it pings Redis), the Service stops sending it traffic and visitors get a 503 instead of a lost vote. The worker exits and Kubernetes restarts it until Redis is back. After a restart Redis reloads its disk, so queued votes are still there.
- **Redis Sentinel / Cluster** (rejected): 3 or more pods, and the clients would have to speak Sentinel. poll (`redis-py`) and the worker (Jedis) are configured with a plain host, and the application is fixed. Real high availability for a queue that is empty most of the time is not worth it.
- **Azure Cache for Redis** (rejected): paid whether the cluster runs or not, and outside the cluster the evaluator gives us.

## `templates/redis/statefulset.yaml`

### Identity and data retention

```yaml
spec:
  serviceName: redis-headless
  replicas: 1
  persistentVolumeClaimRetentionPolicy:
    whenDeleted: Retain
    whenScaled: Retain
```

Same as PostgreSQL ([explained there](postgres.md#identity-and-data-retention), and in general in [k8s-statefulset.md](k8s-statefulset.md#how-the-chart-sets-it-up)): one replica, a headless Service for the pod's DNS name, and the disk is kept when the StatefulSet is deleted. Here the disk holds the votes not yet processed.

### Configuration through arguments

```yaml
args:
  - --requirepass
  - $(REDIS_PASSWORD)
  - --appendonly
  - "yes"
  - --appendfsync
  - everysec
  - --maxmemory
  - {{ .Values.redis.maxmemory | quote }}
  - --maxmemory-policy
  - noeviction
```

The image's entrypoint turns a first argument starting with `-` into `redis-server <arguments>`, so Redis takes its settings from the command line and the chart needs no `redis.conf` and no ConfigMap. Checked in the pod with `redis-cli config get`:

| Argument | Effect | Why |
|---|---|---|
| `--requirepass $(REDIS_PASSWORD)` | Every command needs the password. | Without it, any pod of the cluster can read or delete the votes. |
| `--appendonly yes` | Every write is also appended to a file (AOF) on the disk. | Without it, Redis only writes snapshots now and then (`save` rules), and a crash loses everything since the last one. |
| `--appendfsync everysec` | The file is flushed to disk once per second. | A crash loses at most about one second of votes. `always` flushes after every write: no loss, but one disk write per vote on a billed disk; `no` leaves it to the operating system, up to 30 s of loss. |
| `--maxmemory 192mb` | Redis refuses to store more than this. | See [Memory and CPU](#memory-and-cpu). |
| `--maxmemory-policy noeviction` | When full, new writes get an error instead of Redis deleting old data. | The default policy for a cache is to evict keys; here the only key is the queue, and dropping its entries means silently losing votes. |

- **`$(REDIS_PASSWORD)`**: Kubernetes (not a shell) replaces `$(NAME)` in `args` with the value of the environment variable. The pod spec keeps the literal `$(REDIS_PASSWORD)` (`kubectl get pod redis-0 -o jsonpath='{.spec.containers[0].args}'`), so the password is never written in it. Arguments are an array and not a shell string, so a password with spaces or quotes (a Secret of your own) cannot break the command.
- **`"yes"` is quoted**: unquoted, YAML reads `yes` as a boolean, and an argument must be a string.
- **The password is visible inside the container** in the process list (`ps`), as with any `--requirepass`. Only someone who can already exec into the pod sees it, and that person can read the environment variable anyway.

### Running as the redis user

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 999
  runAsGroup: 999
  fsGroup: 999
  fsGroupChangePolicy: OnRootMismatch
```

The image normally starts as root, fixes the owner of `/data` and drops to the `redis` user. Starting directly as that user removes root from the container (`id` prints `uid=999(redis) gid=999(redis)`). `fsGroup` lets it write to the fresh Azure disk, which belongs to root, exactly as for [PostgreSQL](postgres.md#running-as-the-postgres-user). The container also drops every Linux capability and cannot gain privileges.

### The data volume

```yaml
volumeMounts:
  - name: data
    mountPath: /data
```

The image's working directory and volume is `/data` (`config get dir` prints `/data`): Redis writes its AOF files there, in a `appendonlydir` folder. The volume template is the same as PostgreSQL's (`ReadWriteOnce`, `managed-csi`, selector labels only so that the next Redis bump does not make `helm upgrade` fail).

### Probes

```yaml
startupProbe:
  exec:
    command: ["sh", "-c", "test \"$(redis-cli ping)\" = PONG"]
  periodSeconds: 2
  failureThreshold: 30
readinessProbe:      # same command
  periodSeconds: 5
livenessProbe:       # same command
  periodSeconds: 10
  failureThreshold: 6
```

All three run the same check: ask Redis `PING` and require the answer `PONG`.

- **`REDISCLI_AUTH`**: `redis-cli` reads its password from this environment variable, set from the same Secret as `REDIS_PASSWORD`. The alternative, `redis-cli -a "$REDIS_PASSWORD"`, puts the password in the process list and prints a warning (hence `--no-auth-warning`, which the issue proposed). The variable needs neither.
- **Why compare with `PONG` instead of trusting the exit code (a trap found while testing).** `redis-cli` exits 0 whatever Redis answers. Without the password it prints `NOAUTH Authentication required.` and exits 0 (checked: `exit=0`). More importantly, after a restart Redis replays its AOF file and answers `LOADING Redis is loading the dataset in memory` to every command: a probe that only checks the exit code would mark Redis ready while it cannot serve anything. With the comparison, only `PONG` counts, and a wrong password also fails the probe (`exit code 1`).
- **Startup probe**: up to 30 × 2 s = 1 min before the other probes take over; replaying a large AOF file is the slow case.
- **Liveness tolerates 6 × 10 s** of failures so a short stall does not restart a Redis that is busy loading or rewriting its file.

The pod template carries a `checksum/redis-secret` annotation, like worker and result will, so a new password rolls the pod ([helm-chart.md](helm-chart.md#restarting-pods-when-a-password-changes)). The generated password never changes, so its checksum is constant.

### Node drain

No PodDisruptionBudget on Redis, for the reason given for PostgreSQL ([postgres.md](postgres.md#node-drain)): a budget on a single pod would block every drain. During a drain poll is NotReady (its `/readyz` pings Redis) until the pod is back with its append-only file; votes already queued are kept. See [helm-availability.md](helm-availability.md#redis-and-postgresql-no-pdb-on-purpose).

### Memory and CPU

```yaml
resources:
  requests: {cpu: 50m, memory: 256Mi}
  limits:   {cpu: 250m, memory: 256Mi}
maxmemory: 192mb
```

The memory request equals the limit (guaranteed memory, last to be evicted). QoS class **Burstable**, see [resources.md](resources.md).

- **`maxmemory` (192 MB) is below the container's memory limit (256 MiB)** on purpose. Redis needs room beyond its data: the process itself, buffers, and the AOF rewrite, when it forks a child that can use extra memory while the parent keeps writing. If `maxmemory` equalled the limit, the kernel would kill the container (`OOMKilled`) before Redis could refuse a write. Below it, Redis answers the error itself and keeps running. A queue of tiny JSON votes (about 100 bytes each) would take millions of entries to fill 192 MB.
- **What a full Redis does** (checked by lowering `maxmemory` to 2 MB and pushing 4 KB values): `OOM command not allowed when used memory > 'maxmemory'.` after 140 pushes, no key evicted (`evicted_keys:0`), the votes already queued still there. poll then fails the vote with an error rather than the worker losing it.
- **How to limit the processing power of Redis** (a defense question): the container's CPU **limit**, here `250m`, enforced by the kernel (CFS quota, see [resources.md](resources.md#cfs-quota-and-throttling)): Redis is throttled past a quarter of a core. Redis runs commands on a **single thread**, so a limit above 1 CPU would never be used, and the request (`50m`) is what the scheduler reserves. Memory is limited twice: `maxmemory` inside Redis, `limits.memory` outside.
- **A CPU limit slows Redis rather than protecting a neighbour**, since requests already guarantee its share. It is kept because the issue asks for an explicit answer and because a vote queue is nowhere near 0.25 CPU.

## Services

`templates/redis/service.yaml` holds two Services, like PostgreSQL's ([explained there](postgres.md#services)):

| Service | `clusterIP` | Used by |
|---|---|---|
| `redis` | a virtual IP | poll and worker (`REDIS_HOST=redis`). The port is **6379**, which cannot change: the worker hardcodes it. The name is not release-prefixed for the same reason. |
| `redis-headless` | `None` | the StatefulSet (`serviceName`): `redis-0.redis-headless.<namespace>.svc` |

The container port is named `redis` and both Services target it by name.

## Keeping and deleting the data

| Action | Data |
|---|---|
| `kubectl delete pod redis-0`, node drain, `helm upgrade` | Kept: the new pod mounts the same disk and replays the AOF file. |
| `helm uninstall` | Kept: the PVC is not a Helm object and the retention policy is `Retain`. |
| `kubectl -n bernstein delete pvc data-redis-0` | **Deleted** with the Azure disk, and the queued votes with it. Also stops its billing. |

The disk is billed even when the cluster is stopped: 1 GiB is billed as a 4 GiB **E1 ZRS** disk, 0.396 €/month ([cost.md](cost.md)). Azure's smallest managed disk is 4 GiB, so requesting less would not save anything.

## Password

### `templates/redis/secret.yaml`

```yaml
{{- if not .Values.redis.existingSecret }}
{{- $name := include "bernstein.secretName" (dict "context" $ "component" "redis") }}
{{- /* Reuse the password of the Secret already in the cluster, ... */}}
{{- $current := lookup "v1" "Secret" .Release.Namespace $name | dig "data" "password" "" }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ $name }}
  labels:
    {{- include "bernstein.labels" (dict "context" $ "component" "redis") | nindent 4 }}
type: Opaque
data:
  password: {{ $current | default (randAlphaNum 32 | b64enc) | quote }}
{{- end }}
```

- **`if not .Values.redis.existingSecret`**: with an existing Secret, the file renders to nothing.
- **`$name`**: `redis-credentials`, from the same helper the pods use ([helm-helpers.md](helm-helpers.md#bernsteinsecretname)). Stored in a variable because it is needed twice.
- **`randAlphaNum 32`**: 32 random letters and digits. No special characters, so the value is safe on Redis' command line (`--requirepass`, #18) without any quoting.
- **`| b64enc`**: values under a Secret's `data` must be base64-encoded.

### The trap: a random value changes on every render

Helm renders every template again on each `helm upgrade`. A plain `password: {{ randAlphaNum 32 | b64enc }}` would therefore give Redis a **new password on every deploy**, while the pods that already run still hold the old one: authentication failures until everything restarts.

`lookup` fixes it. It asks the cluster for an object, here the current `redis-credentials` Secret in the release namespace:

1. `lookup "v1" "Secret" .Release.Namespace $name` returns the Secret as a map, or an empty map if it does not exist.
2. `| dig "data" "password" ""` takes `data.password` from it, or `""` if the Secret or the key is missing. The value is already base64, as stored by Kubernetes, so it is reused as is.
3. `$current | default (randAlphaNum 32 | b64enc)`: the existing password if there is one, else a new random one.

A password is therefore generated **once, on first install**, and kept by every upgrade and rollback.

### `lookup` without a cluster

`helm template` and `helm install --dry-run=client` do not contact the cluster, so `lookup` returns an empty map and a new password appears on every run. That is expected: only a real `install` / `upgrade` (or `--dry-run=server`) reads the cluster.

The identity running `helm upgrade` also needs the `get` permission on Secrets in the namespace for `lookup` to work. That matters for the CI role (#34).

### Bringing your own Secret

```sh
kubectl -n bernstein create secret generic redis-auth --from-literal=password="$(openssl rand -hex 32)"
helm upgrade --install bernstein charts/bernstein -n bernstein ... --set redis.existingSecret=redis-auth
```

The Secret must have a `password` key. Pods restart when its content changes, through the checksum annotation ([helm-chart.md](helm-chart.md#restarting-pods-when-a-password-changes)).

### If `redis-credentials` is deleted

The next upgrade finds no Secret and generates a new password. The generated password has a constant checksum (it is never supposed to change), so nothing restarts by itself: restart Redis, poll and the worker so they all pick up the new one, e.g. `kubectl -n bernstein rollout restart statefulset/redis deployment/poll deployment/worker`.

## Verifying

```sh
OK="--set global.registry=example.azurecr.io --set-string global.tag=dev --set-string postgres.password=x"

# 32 characters; a different value on each run, since there is no cluster to look up
helm template bernstein charts/bernstein $OK -s templates/redis/secret.yaml \
  | awk '/password:/ {print $2}' | tr -d '"' | base64 -d | wc -c
```

That the password is kept across upgrades can only be checked on a cluster ([local cluster](helm-chart.md#testing-on-a-local-cluster)), by comparing it before and after `helm upgrade`:

```sh
kubectl -n bernstein get secret redis-credentials -o jsonpath='{.data.password}'
```

Checked on 2026-10-12 on a local Kubernetes 1.36.1 cluster: the same value after `helm install` and two `helm upgrade` runs.

## Verifying (StatefulSet)

Without a cluster:

```sh
OK="--set global.registry=example.azurecr.io --set-string global.tag=dev --set-string postgres.password=x"
helm lint --strict charts/bernstein $OK
helm template bernstein charts/bernstein $OK | nix shell nixpkgs#kubeconform -c kubeconform -strict -summary -kubernetes-version 1.36.0

# Rejected by the schema
helm template bernstein charts/bernstein $OK --set redis.maxmemory=lots
#   - at '/redis/maxmemory': 'lots' does not match pattern '^[1-9][0-9]*(kb|mb|gb)$'
```

On a local cluster ([how](helm-chart.md#testing-on-a-local-cluster)), checked on 2026-10-13 with Kubernetes 1.36.1. The worker image cannot be pulled there (it comes from our ACR, #12), so its role is played with `redis-cli`:

| Check | Command | Result |
|---|---|---|
| Starts | `helm install --wait` | `redis-0` Ready in 20 s, with PVC `data-redis-0` Bound |
| Non-root | `kubectl -n bernstein exec redis-0 -- id` | `uid=999(redis) gid=999(redis)` |
| Settings applied | `redis-cli config get appendonly` (and the others) | `appendonly yes`, `appendfsync everysec`, `maxmemory 201326592`, `maxmemory-policy noeviction`, `dir /data` |
| No password | `redis-cli ping` without `REDISCLI_AUTH` | `NOAUTH Authentication required.` |
| Wrong password | `REDISCLI_AUTH=wrong redis-cli ping` | `AUTH failed: WRONGPASS invalid username-password pair or user is disabled.` |
| Password not in the spec | `kubectl get pod redis-0 -o jsonpath='{.spec.containers[0].args}'` | `["--requirepass","$(REDIS_PASSWORD)",...]` |
| Votes survive a restart | `RPUSH votes ...` three times, `kubectl delete pod redis-0`, `LLEN votes` | 3 before, 3 after, same content; the log says `DB loaded from append only file` |
| Limits visible | `kubectl describe pod redis-0` | `Limits: cpu 500m, memory 256Mi`, `Requests: cpu 50m, memory 128Mi` |
| Upgrade keeps the password and the data | `helm upgrade`, compare the Secret, `LLEN votes` | same Secret value, queue intact, pod rolled once (probe change) |
| Full memory | `config set maxmemory 2mb`, push 4 KB values | `OOM command not allowed when used memory > 'maxmemory'.` after 140 pushes; `evicted_keys:0`; earlier vote still queued |
| Probe | `sh -c 'test "$(redis-cli ping)" = PONG'` | exit 0 with the right password, exit 1 with a wrong one |

The acceptance criterion "votes cast while the worker is scaled to 0 are still processed afterwards" needs the worker image; its first half (votes survive `kubectl delete pod redis-0`) is checked above, the second is verified once #20 and #12 land. `fsGroup` ownership can only be checked on AKS: the local cluster's volumes ignore it.
