# Result

What we ship for result, and why. Today this covers the image (`poll-application/result/Dockerfile`, #10); the Deployment and Service (#21) and live updates across replicas (#26) will be added here.

## Role in the application

result is a Node.js (Express + Socket.IO) web app: it reads the vote counts from PostgreSQL and pushes them to browsers over a websocket. It listens on **port 80** (hardcoded in `server.js`) and serves `/healthz` and `/readyz`.

## What we ship

| Object | File | Issue |
|---|---|---|
| Container image | `poll-application/result/Dockerfile` | #10 |
| Deployment, Service | — | #21 (planned) |

## The image

```dockerfile
FROM node:24-slim@sha256:d6aa754f...

ENV NODE_ENV=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY . .

USER 1000

EXPOSE 80

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["node", "server.js"]
```

### tini as PID 1

The process started by `CMD` is PID 1 in the container. The kernel treats PID 1 specially: a signal it has no handler for is **ignored**, instead of applying the default action (terminate). Node installs no SIGTERM handler, and `server.js` does not add one, so `node server.js` as PID 1 ignores the SIGTERM sent by Kubernetes (and `docker stop`). The pod then waits the whole `terminationGracePeriodSeconds` (30 s by default) and is SIGKILLed, cutting open websockets abruptly. That makes every rollout slow, which hurts the zero-downtime demo (#25).

`tini` is a tiny init: it runs as PID 1, starts `node` as its child (a normal process, so default signal actions apply), forwards signals to it, and reaps zombie processes. Process 1 in the new image:

```
$ docker exec rt cat /proc/1/cmdline
/usr/bin/tini -- node server.js
```

Measured with `docker stop -t 10` (same mechanism as a pod deletion, SIGTERM then SIGKILL after the timeout):

| Image | Stop time | Exit code |
|---|---|---|
| Before (`node` as PID 1) | 10210 ms | 137 (SIGKILL after the timeout) |
| After (`tini`) | 199 ms | 143 (SIGTERM) |

Rejected:

- **Handling SIGTERM in `server.js`**: cleaner (could close the server before exiting), but the application code is treated as fixed.
- **`docker run --init`**: Docker only; Kubernetes has no equivalent flag.
- **`shareProcessNamespace: true`** on the pod (the pause container becomes PID 1): changes process visibility between containers for the whole pod, heavier than one package.

### Non-root user and port 80

The official Node image already has a `node` user (UID 1000); `USER 1000` runs the app as it. The UID is written numerically because hadolint (CI lint job, threshold `info`) rejects a name with `DL3066 info: Non-numeric user-id may not be resolvable by host system`, and Kubernetes `runAsNonRoot` can only verify a numeric user:

```
$ docker run --rm --entrypoint id result:test
uid=1000(node) gid=1000(node) groups=1000(node)
```

Files copied into `/app` stay owned by root: the app only reads them, and cannot modify its own code.

Port 80 as non-root needs the pod sysctl `net.ipv4.ip_unprivileged_port_start=0`, set in the Deployment (#21), for the same reasons as poll and the worker (see [worker.md](worker.md#non-root-user-and-port-80)). Docker sets it to 0 by default, so `docker run` works locally.

### Dependencies and size

- `package.json` and `package-lock.json` are copied before the source, so `npm ci` is cached until dependencies change.
- `npm ci --omit=dev` installs exactly the lockfile, without development dependencies; `npm cache clean --force` drops the download cache from the layer.
- `NODE_ENV=production` makes Express use its production mode (view caching, less verbose errors).
- `.dockerignore` excludes `node_modules/`, so a local `node_modules` (possibly built for another OS) never overwrites the one installed in the image.
- `tini` is installed with `--no-install-recommends` and the apt lists are removed in the same layer.

### Pinned base image

`node:24-slim` is pinned by digest, like poll and the worker: rebuilds are reproducible and base updates come as reviewed PRs (#13). To update it:

```sh
docker pull node:24-slim
docker inspect --format '{{index .RepoDigests 0}}' node:24-slim
```

## Checks

```sh
docker build -t result:test poll-application/result
docker run -d --name rt -p 18081:80 result:test
curl localhost:18081/healthz      # OK (200)
docker stop -t 10 rt              # returns in well under a second
docker inspect rt --format '{{.State.ExitCode}}'   # 143
docker rm rt
```
# result

What the chart deploys for `result`, the live results page, and why. Passwords in general are covered in [helm-chart.md](helm-chart.md#passwords).

## Role in the application

result is a Node.js application (Express + Socket.IO). Once a second it runs `SELECT vote, COUNT(id) ... GROUP BY vote` on PostgreSQL and pushes the tally to every connected browser over a websocket. It stores nothing itself, so it is a Deployment ([k8s-statefulset.md](k8s-statefulset.md#what-it-is) compares the two controllers).

Behaviors in `poll-application/result/server.js` that drive the manifest:

- The HTTP server starts listening on port 80 **immediately**; the database connection is made in the background with up to 1000 attempts, 1 s apart.
- On any database error after connecting (a lost connection or a failed query) the process calls `process.exit(1)` and relies on Kubernetes to restart it.
- `/healthz` always answers 200. `/readyz` answers 200 only if `SELECT 1` succeeds, 503 otherwise (and while not yet connected).

## What the chart deploys

| Object | File | Issue |
|---|---|---|
| Deployment `result`: 1 pod | `templates/result/deployment.yaml` | #21 |
| Service `result:80`: stable address, target of the Gateway (#22) | `templates/result/service.yaml` | #21 |

## Values

```yaml&
result:
  image:
    repository: result
    tag: ""
  replicas: 2
  resources:
    requests:
      cpu: 50m
      memory: 96Mi
    limits:
      memory: 192Mi
```

| Key | Meaning |
|---|---|
| `image.*` | Built by CI and pushed to our registry ([helm-chart.md](helm-chart.md#per-component-image-blocks)). Empty `tag` means `global.tag`. |
| `replicas` | Number of pods, **two** so an update or a drain always leaves one. Socket.IO opens a session on one pod and the next request must reach the same pod, otherwise the browser gets "Session ID unknown"; the Gateway pins each browser to a pod with a cookie ([gateway.md](gateway.md#traefikserviceyaml-sticky-sessions-for-result-26)). Schema: integer, at least 1. |
| `autoscaling` | Same HorizontalPodAutoscaler as poll ([helm-autoscaling.md](helm-autoscaling.md)), **disabled** (`enabled: false`) until #26: scaling out needs sticky sessions. The `replicas` line of the Deployment is only rendered while it is off. To turn it on after #26: `--set result.autoscaling.enabled=true`. |
| `replicas` | Number of pods. **One for now**: Socket.IO opens a session on one pod and the next request must reach the same pod, otherwise the browser gets "Session ID unknown" and the page shows nothing. Going above 1 needs sticky sessions at the Gateway (#26). Schema: integer, at least 1. |
| `resources` | CPU and memory of the container. Starting values; #30 sets requests and limits for every workload. |

## `templates/result/deployment.yaml`

### Rolling update without errors

Same settings as poll ([poll.md](poll.md#rolling-update-without-errors)): `maxUnavailable: 0`, `maxSurge: 1`, `minReadySeconds: 5`, `revisionHistoryLimit: 5`, a `preStop` sleep of 10 s and `terminationGracePeriodSeconds: 40`. Differences:

- Readiness is probed every 2 s (instead of 5 s) so that the replacement joins quickly. The poll trap does not apply here: Node answers `/readyz` on its event loop and does not hold a thread.
- Node exits at once on SIGTERM (tini forwards it, the server has no handler), so the `preStop` sleep is what lets Traefik drop the pod first.
- With a single replica, HTTP has no gap (the surge pod is Ready before the old one goes), but open Socket.IO connections are cut when the old pod stops; the browser reconnects by itself.

See [ADR-0005](adr/0005-zero-downtime-rolling-updates.md).

### Environment

```yaml
env:
  - name: POSTGRES_HOST
    value: postgres
  - name: POSTGRES_PORT
    value: "5432"
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

- **`POSTGRES_HOST=postgres`**: the Service name, fixed and not prefixed by the release ([postgres.md](postgres.md)).
- **`POSTGRES_DB` and `POSTGRES_USER`** come from the same values that create the database, so they cannot drift apart.
- **`POSTGRES_PORT` is quoted** (`"5432"`): environment values must be strings; an unquoted number is rejected by the API server.
- **`POSTGRES_PASSWORD`** comes from the Secret through `secretKeyRef`, never as a literal, whether the chart created it or it is `postgres.existingSecret`.
- **`checksum/postgres-secret`** on the pod template: result reads the password once at start, so a new password rolls the pods ([helm-chart.md](helm-chart.md#restarting-pods-when-a-password-changes)).

### Port 80 as a non-root user

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  sysctls:
    - name: net.ipv4.ip_unprivileged_port_start
      value: "0"
```

Same reasoning as poll ([poll.md](poll.md#port-80-as-a-non-root-user)): the server listens on port 80, which only root may bind unless the pod lowers `net.ipv4.ip_unprivileged_port_start`, a sysctl on Kubernetes' safe list. UID 1000 is the `node` user that the `node:24-slim` base image ships. The current Dockerfile does not set `USER`, so the container would run as root without this; `runAsNonRoot` makes the kubelet refuse to start it as root. Hardening the Dockerfile is #10; if it picks another UID, change `runAsUser` here.

### Probes

```yaml
startupProbe:   {httpGet: {path: /healthz, port: http}, periodSeconds: 2, failureThreshold: 30}
readinessProbe: {httpGet: {path: /readyz,  port: http}, periodSeconds: 5, timeoutSeconds: 3, failureThreshold: 2}
livenessProbe:  {httpGet: {path: /healthz, port: http}, periodSeconds: 10, timeoutSeconds: 3, failureThreshold: 3}
```

| Probe | Endpoint | Question | Effect of failing |
|---|---|---|---|
| startup | `/healthz` | Has the server started? Up to 30 × 2 s. | The other probes wait. |
| readiness | `/readyz` | Does `SELECT 1` succeed? | The pod leaves the Service's endpoints: no traffic, **no restart**. |
| liveness | `/healthz` | Is the process alive and answering? | The container is restarted. |

**Liveness must not look at PostgreSQL.** A database outage would otherwise fail the liveness probe of every pod at once, and restarting result does not bring PostgreSQL back. The process already exits by itself on a lost connection, so Kubernetes restarts it with its normal back-off; while the database is unreachable the pod is simply not Ready.

The startup probe uses `/healthz`, not `/readyz`, because the server listens before the database is reachable: it covers a slow start of the process, while the 1000 s connection retry loop is covered by readiness (not Ready until connected).

Unlike poll, `/readyz` here does not hang when the database is down: it answers 503 at once while not connected, and a query on a dead connection ends in the process exiting. So the poll trap (readiness requests holding all server threads, [poll.md](poll.md#the-trap-readiness-probes-can-starve-the-liveness-probe)) does not apply: Node.js handles requests on one event loop, not a fixed thread pool. This was reasoned from the code, not measured yet.

### Resources

```yaml
resources:
  requests: {cpu: 50m, memory: 128Mi}
  limits:   {cpu: 300m, memory: 256Mi}
```

One Node.js process doing one small query per second. The memory limit stops a leak from taking the node; the CPU limit caps it at 0.3 core and the CPU request is the base of the autoscaler's utilisation (#29). QoS class **Burstable**. See [resources.md](resources.md) and [ADR-0006](adr/0006-cpu-limits.md). The numbers are starting points, to be checked with `kubectl top` under load.

## `templates/result/service.yaml`

```yaml
spec:
  type: ClusterIP
  selector:
    {{- include "bernstein.selectorLabels" (dict "context" $ "component" "result") | nindent 4 }}
  ports:
    - name: http
      port: 80
      targetPort: http
```

A `ClusterIP` Service gives result a stable address, `result:80`, and sends connections only to pods that are Ready. It is not public: the Gateway (#22) is the single entry point, and each `LoadBalancer` Service would add a billed public IP ([cost.md](cost.md)).

## Verifying

Without a cluster:

```sh
OK="--set global.registry=example.azurecr.io --set-string global.tag=dev --set-string postgres.password=x"
helm lint --strict charts/bernstein $OK
helm template bernstein charts/bernstein $OK | nix shell nixpkgs#kubeconform -c kubeconform -strict -summary -kubernetes-version 1.36.0
# Summary: 14 resources found parsing stdin - Valid: 14, Invalid: 0, Errors: 0, Skipped: 0

# Rejected by the schema
helm template bernstein charts/bernstein $OK --set result.replicas=0   # at '/result/replicas': minimum: got 0, want 1
```

The acceptance criteria of #21 (live counts within about 1 s of a vote, recovery after a PostgreSQL restart) need a running cluster and have **not been run yet**; this section gets the table of checks once they are.
