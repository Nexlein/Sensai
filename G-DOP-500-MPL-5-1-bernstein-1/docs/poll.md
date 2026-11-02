# poll

What the chart deploys for `poll`, the voting page, and why. Passwords in general are covered in [helm-chart.md](helm-chart.md#passwords).

## Role in the application

poll is a Flask application served by gunicorn. It shows the four choices, and pushes each vote as JSON onto the Redis list `votes` (`RPUSH`). It stores nothing itself, so it is **stateless**: any pod can serve any visitor, and pods can be created, deleted or replaced freely. That is why it is a Deployment ([k8s-statefulset.md](k8s-statefulset.md#what-it-is) compares the two controllers).

The page also prints the name of the pod that served it (`hostname`), which makes load balancing visible in the demo.

## What the chart deploys

| Object | File | Issue |
|---|---|---|
| Deployment `poll`: 2 pods | `templates/poll/deployment.yaml` | #19 |
| Service `poll:80`: stable address, target of the Gateway (#22) | `templates/poll/service.yaml` | #19 |

## Values

```yaml
poll:
  image:
    repository: poll
    tag: ""
  replicas: 2
  options:
    a: Ansible
    b: Chef
    c: Puppet
    d: SaltStack
  resources:
    requests:
      cpu: 50m
      memory: 128Mi
    limits:
      memory: 256Mi
```

| Key | Meaning |
|---|---|
| `image.*` | Built by CI and pushed to our registry ([helm-chart.md](helm-chart.md#per-component-image-blocks)). Empty `tag` means `global.tag`. |
| `replicas` | Number of pods. Two, so one can be lost or restarted without downtime. Schema: integer, at least 1. The autoscaler (#29) will take this number over. |
| `options.a` to `options.d` | The four labels shown on the page (`OPTION_A` to `OPTION_D`). Schema: all four required, non-empty, nothing else allowed. |
| `resources` | CPU and memory of the container. Starting values; #30 sets requests and limits for every workload. |

## `templates/poll/deployment.yaml`

### Replicas and selector

```yaml
spec:
  replicas: {{ .Values.poll.replicas }}
  selector:
    matchLabels:
      {{- include "bernstein.selectorLabels" (dict "context" $ "component" "poll") | nindent 6 }}
```

The selector is how the Deployment finds its pods; it uses the selector labels, which never change for the life of a release ([helm-helpers.md](helm-helpers.md)). The pod template carries the full labels, which include the image tag as `app.kubernetes.io/version`.

With the autoscaler on (the default), the `replicas` line is not rendered at all:

```yaml
  {{- if not .Values.poll.autoscaling.enabled }}
  replicas: {{ .Values.poll.replicas }}
  {{- end }}
```

Why: the autoscaler changes the live `replicas`, and a manifest that also wrote it would reset the count on every `helm upgrade`. The trap on the first upgrade of an older release is in [helm-autoscaling.md](helm-autoscaling.md#the-deployment-must-not-set-replicas).

### Autoscaling

`templates/poll/hpa.yaml` renders a HorizontalPodAutoscaler: 2 to 5 pods, target 70 % of the CPU request (35m per pod), scale-down window 120 s. What it is, how the values work, the demo and the rejected alternatives are in [helm-autoscaling.md](helm-autoscaling.md).

### Rolling update without errors

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate: {maxUnavailable: 0, maxSurge: 1}
minReadySeconds: 5
revisionHistoryLimit: 5
...
terminationGracePeriodSeconds: 40
...
lifecycle:
  preStop:
    sleep: {seconds: 10}
```

- `maxUnavailable: 0` + `maxSurge: 1`: a third pod is started, and an old one is only removed once the new one is Ready (and has stayed so for `minReadySeconds: 5`). Serving capacity never drops below 2.
- `preStop` sleep: on deletion the kubelet sends SIGTERM at the same time as the endpoint is removed, and Traefik learns of the removal a moment later. Without the sleep, requests reach a pod already shutting down (connection refused / 502). With it, the pod keeps serving 10 s, then gunicorn gets SIGTERM and finishes in-flight requests within its `graceful_timeout` of 20 s. The native `sleep` action needs no binary in the image (Kubernetes ≥ 1.30).
- `terminationGracePeriodSeconds: 40` is above 10 s + 20 s, and the preStop time counts inside it.
- Readiness stays at `periodSeconds: 10` (see [the trap](#the-trap-readiness-probes-can-starve-the-liveness-probe)): a new pod can take up to 10 s to join, which only slows the rollout.
- A Secret change rolls the pods through the `checksum/redis-secret` annotation; the option labels are in the template, so changing them also rolls.

The full timeline and the rejected alternatives (blue/green, readiness-only tuning) are in [ADR-0005](adr/0005-zero-downtime-rolling-updates.md).

### Environment

```yaml
env:
  - name: REDIS_HOST
    value: redis
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ include "bernstein.secretName" (dict "context" $ "component" "redis") }}
        key: password
  - name: OPTION_A
    value: {{ .Values.poll.options.a | quote }}
  ...
```

- **`REDIS_HOST=redis`**: the Service name, which is fixed and not prefixed by the release ([redis.md](redis.md)). poll does not need the port: the client defaults to 6379.
- **`REDIS_PASSWORD`** comes from the Secret through `secretKeyRef`, never as a literal, whether the chart generated it or it is `redis.existingSecret`.
- **`OPTION_A` to `OPTION_D`** are plain values. Changing one and running `helm upgrade` changes the pod template, so Kubernetes rolls the pods: no image rebuild is needed to relabel a choice, which is handy during a demo.
- **`| quote`** writes the value as a YAML string, so a label such as `Yes` or `42` is not read as a boolean or a number.
- **`checksum/redis-secret`** on the pod template: poll reads the Redis password at start, so a new password rolls the pods ([helm-chart.md](helm-chart.md#restarting-pods-when-a-password-changes)).

### Port 80 as a non-root user

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  sysctls:
    - name: net.ipv4.ip_unprivileged_port_start
      value: "0"
```

- The image runs as user `app` (UID 10001, created by the Dockerfile) and gunicorn listens on **port 80** (`bind = "0.0.0.0:80"`). On Linux only root may bind a port below 1024.
- **`net.ipv4.ip_unprivileged_port_start`** is the lowest port a non-root process may bind. Setting it to 0 in the pod lets UID 10001 bind 80. It is one of the sysctls Kubernetes considers *safe*: it applies to the pod's own network namespace and affects no other pod, so it needs no cluster-wide permission. Checked in the pod: `cat /proc/sys/net/ipv4/ip_unprivileged_port_start` prints `0`, `id` prints `uid=10001(app)`.
- The alternatives were adding the `NET_BIND_SERVICE` capability (a Linux capability on the container, which the chart otherwise drops entirely) or changing the application's port (the Dockerfile and the application's documented port are fixed).
- The container drops every capability and cannot gain privileges. A read-only root filesystem and a seccomp profile are #33.

### Probes

```yaml
startupProbe:
  httpGet: {path: /healthz, port: http}
  periodSeconds: 2
  failureThreshold: 30
readinessProbe:
  httpGet: {path: /readyz, port: http}
  periodSeconds: 10
  timeoutSeconds: 6
  failureThreshold: 2
livenessProbe:
  httpGet: {path: /healthz, port: http}
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3
```

| Probe | Endpoint | Question | Effect of failing |
|---|---|---|---|
| startup | `/healthz` | Has gunicorn started? Up to 30 × 2 s. | The other probes wait. |
| readiness | `/readyz` | Does Redis answer `PING`? | The pod leaves the Service's endpoints: no traffic, **no restart**. |
| liveness | `/healthz` | Is the process alive and answering? | The container is restarted. |

**Liveness must not look at Redis.** If it did, a Redis outage would fail the liveness probe of every poll pod at once and Kubernetes would restart them all, for nothing: restarting poll does not bring Redis back. Readiness is the right place for the dependency: the pods stop receiving visitors and come back when Redis does. Visitors are refused at the entry point (#22) instead of reaching a half-working pod that fails on every vote.

### The trap: readiness probes can starve the liveness probe

While Redis is down, `/readyz` does not answer quickly with a 503. redis-py retries a failed connection several times, and the request takes about **32 seconds** to return (measured: `/readyz -> 503 after 31.9s`, redis-py 8.1.0). The kubelet gives up after `timeoutSeconds: 6` and marks the probe failed, but **gunicorn keeps the request, and its thread, until it finishes**. gunicorn here has 2 workers × 4 threads = 8 threads per pod.

With the readiness probe every 5 seconds, about 6 requests were always hanging, so the threads filled up and `/healthz` could not get one. With Redis scaled to 0 for 3 minutes, the liveness probe failed and **both poll pods were restarted** (`restarts=1` each):

```text
Liveness probe failed: Get "http://10.244.0.11:80/healthz": context deadline exceeded (Client.Timeout exceeded while awaiting headers)
```

That is exactly the restart storm the liveness design is meant to prevent, and it breaks the acceptance criterion "poll pods become NotReady but are not restarted". It only appears after more than a minute of outage, so a short test does not show it.

The fix is the readiness `periodSeconds: 10`: about 3 requests hang at a time instead of 6, and threads remain free. Checked again with Redis down for 4 minutes: 24 `/healthz` calls in a row answered in about 1 ms, and `restarts=0`. The price is that a pod notices Redis coming back up to 10 s later (measured: both pods Ready 2 s after Redis returned, since the next probe happened to be close).

If more margin is needed later, the lever is in the image's runtime configuration: more gunicorn threads or workers (`WEB_CONCURRENCY` already sets the workers) so that hanging probes cannot use them all.

### Resources

```yaml
resources:
  requests: {cpu: 50m, memory: 128Mi}
  limits:   {cpu: 500m, memory: 256Mi}
```

The requests reserve room on a node and are the base of the autoscaler's CPU utilisation (#29: 70 % of 50m = 35m per pod). The memory limit stops a leak from taking the node (the container is restarted instead). The CPU limit caps a noisy pod at half a core; it throttles gunicorn only when it is using more than that. gunicorn runs 2 worker processes, so the memory covers both. QoS class **Burstable**; the trade-off of CPU limits and the quota mechanism are explained in [resources.md](resources.md) and [ADR-0006](adr/0006-cpu-limits.md). The numbers are starting points, to be checked with `kubectl top` under load.

## `templates/poll/service.yaml`

```yaml
spec:
  type: ClusterIP
  selector:
    {{- include "bernstein.selectorLabels" (dict "context" $ "component" "poll") | nindent 4 }}
  ports:
    - name: http
      port: 80
      targetPort: http
```

A `ClusterIP` Service gives poll a stable virtual address, `poll:80`, and spreads connections over the pods that are **Ready** (a pod failing its readiness probe is removed from the endpoints). It is not public: the Gateway (#22) is the single entry point, so there is no `LoadBalancer` Service here (each one would add a billed public IP, [cost.md](cost.md)). `targetPort: http` refers to the container port by name, so the number is written once.

## Verifying

Without a cluster:

```sh
OK="--set global.registry=example.azurecr.io --set-string global.tag=dev --set-string postgres.password=x"
helm lint --strict charts/bernstein $OK
helm template bernstein charts/bernstein $OK | nix shell nixpkgs#kubeconform -c kubeconform -strict -summary -kubernetes-version 1.36.0

# Rejected by the schema
helm template bernstein charts/bernstein $OK --set poll.replicas=0      # at '/poll/replicas': minimum: got 0, want 1
helm template bernstein charts/bernstein $OK --set poll.options.a=      # at '/poll/options/a': minLength: got 0, want 1
helm template bernstein charts/bernstein $OK --set poll.options.e=x     # at '/poll/options': additional properties 'e' not allowed
```

On a local cluster ([how](helm-chart.md#testing-on-a-local-cluster)), checked on 2026-10-13 with Kubernetes 1.36.1. The image is built from `poll-application/poll` with Docker and loaded with `kind load docker-image` (the registry image is not pullable there, #12). Redis from #18 was not merged yet, so a plain `redis:8.10.2` Deployment and a Service `redis`, started with `--requirepass` from the chart's own `redis-credentials` Secret, stood in for it.

| Check | How | Result |
|---|---|---|
| Starts as non-root on port 80 | `kubectl exec ... -- id`, `cat /proc/sys/net/ipv4/ip_unprivileged_port_start` | `uid=10001(app)`, `0` |
| Redis missing at start | `kubectl get pods` before the stand-in exists | pods `Running`, `0/1` Ready, no restart |
| Service endpoints | `kubectl get endpoints poll` | both pod IPs once Ready, none while Redis is down |
| A vote is accepted | `curl -d vote=a http://poll/` from a pod | `200`, and `LLEN votes` is `1` |
| Load balancing visible | six `curl http://poll/` | the page shows both pod names, 3 each |
| One pod deleted, page still served | `curl http://poll/` 150 times in 30 s while deleting one pod | 150 × `200`, 0 failures |
| Redis scaled to 0 | `kubectl scale deploy/redis --replicas=0`, wait | pods `0/1` Ready, service answers connection refused (no endpoints), `/healthz` still `200`, `restarts=0` |
| Redis down for 4 minutes | `/healthz` every 10 s | 24 × `200` in about 1 ms, `restarts=0` (after the probe period fix; with 5 s: restarted, see the trap) |
| Redis back | `kubectl scale deploy/redis --replicas=1` | both pods Ready 2 s later |
| `OPTION_A` relabelled | `helm upgrade --set poll.options.a=Terraform` | the page shows `Terraform` instead of `Ansible`, pods rolled |

My first run of the "one pod deleted" check was wrong: a selector deleted both pods, and the 6 failures it showed said nothing about losing one. The second run, deleting exactly one pod by name, is the one in the table.

`fsGroup`-style ownership does not apply (poll writes nothing to disk). Whether the sysctl is allowed on AKS is checked there: `net.ipv4.ip_unprivileged_port_start` is on Kubernetes' safe list, so no kubelet flag is expected to be needed.
