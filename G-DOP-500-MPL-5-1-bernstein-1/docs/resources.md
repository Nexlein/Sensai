# Resource requests and limits

Every container of the chart declares CPU and memory **requests** and **limits**, and the namespace has a `LimitRange` and a `ResourceQuota`. This document explains what each one does, the values chosen, and the answers to the defense questions ("how would you limit the processing power of Redis?", "what is a QoS class?").

## Requests and limits

| | Request | Limit |
|---|---|---|
| Who reads it | the **scheduler** | the **kubelet** and the kernel (cgroups) |
| What it means | "reserve at least this much for me" | "never give me more than this" |
| CPU over the limit | | the container is **throttled** (slowed), never killed |
| Memory over the limit | | the container is **OOMKilled** and restarted |

Without requests, the scheduler places pods blindly (it sees every pod as needing nothing) and the autoscaler cannot compute a utilisation: a HorizontalPodAutoscaler's "70 % CPU" is 70 % *of the request* (#29). Without limits, one leaking pod (the JVM, a runaway query) can use the whole node and get its neighbours evicted.

## Values

| Component | Requests (CPU / memory) | Limits (CPU / memory) | Why |
|---|---|---|---|
| poll | 50m / 128Mi | 500m / 256Mi | gunicorn, 2 processes; request is the autoscaler's base |
| worker | 100m / 256Mi | 500m / 512Mi | JVM heap is 75 % of the limit: 384 MiB |
| result | 50m / 128Mi | 300m / 256Mi | one Node.js process, one query per second |
| redis | 50m / 256Mi | 250m / 256Mi | single-threaded; `maxmemory 192mb` stays under the memory limit |
| postgres | 100m / 512Mi | 1 / 512Mi | `shared_buffers` 128 MiB plus connections |
| schema Job | 10m / 32Mi | 100m / 128Mi | runs `psql -f` once |

The values are starting points, sized so that the whole application fits on the two nodes (2 vCPU each) with room for the autoscaler and the surge pods of a rolling update ([ADR-0005](adr/0005-zero-downtime-rolling-updates.md)). They have **not** yet been measured under load; the acceptance run (`kubectl top pods` under the #27 load, no `OOMKilled`) belongs to the cluster test session.

## QoS classes

Kubernetes derives a **Quality of Service class** from the requests and limits and uses it to decide who is evicted first when a node runs out of memory:

| Class | Condition | Evicted |
|---|---|---|
| Guaranteed | every container has request = limit for both CPU and memory | last |
| Burstable | at least one request or limit, but not Guaranteed | in between |
| BestEffort | no request nor limit anywhere | first |

All our pods are **Burstable**: their CPU request is lower than their CPU limit, which is what allows bursting. Redis and PostgreSQL have their **memory request equal to the limit**, so their memory is guaranteed (the kernel's OOM score favours them) even though the class stays Burstable. Making them fully Guaranteed would need CPU request = limit too, which reserves a core for PostgreSQL permanently: on 2 vCPU nodes shared with an autoscaler, that is too much.

## CFS quota and throttling

A CPU **limit** is enforced by the kernel's Completely Fair Scheduler as a *quota*: in each 100 ms period, the container may run for `limit × 100 ms` of CPU time (a `250m` limit = 25 ms per period). Once the quota is spent, its threads are paused until the next period. That is how to limit the processing power of Redis: `limits.cpu: 250m` ([redis.md](redis.md#memory-and-cpu)).

The cost is **throttling latency**: a request arriving after the quota is spent waits for the next period, even if the node is idle. That is why many guides recommend requests without CPU limits; see [ADR-0006](adr/0006-cpu-limits.md) for why this chart keeps them.

## `templates/namespace/limitrange.yaml`

```yaml
apiVersion: v1
kind: LimitRange
spec:
  limits:
    - type: Container
      defaultRequest: {cpu: 50m, memory: 64Mi}
      default:        {cpu: 200m, memory: 128Mi}
```

A `LimitRange` gives defaults to any container created in the namespace **without** requests or limits (a pod started by hand with `kubectl run`, a sidecar someone forgot). The API server writes the defaults into the pod when it is created. No container of the chart relies on it: the CI step "Check that every container has CPU and memory requests and limits" fails if one does not set its own. It is a safety net, not the mechanism.

## `templates/namespace/resourcequota.yaml`

```yaml
apiVersion: v1
kind: ResourceQuota
spec:
  hard:
    requests.cpu: "2"
    requests.memory: 4Gi
    limits.cpu: "8"
    limits.memory: 8Gi
    pods: "30"
```

A `ResourceQuota` caps the **sum** over the namespace. A pod that would exceed it is refused at creation (`exceeded quota: compute`), which stops a bug or an over-eager autoscaler from consuming the whole cluster. The sizes cover the worst case of the autoscaler at its maximum (5 poll and 5 result pods) plus one surge pod per Deployment during a rollout, with some margin; the real steady state is about 0.5 CPU and 1.7 GiB of requests.

**Trap:** a quota on `requests.*` or `limits.*` makes it mandatory for every new pod to declare them, or the pod is rejected with `must specify limits.cpu`. That is the second reason for the `LimitRange`: it fills the gap before the quota checks.

Both are optional (`namespace.limitRange.enabled`, `namespace.quota.enabled`). They are namespaced objects, so the deploy identity needs no cluster-wide right to create them.

## Verifying

```sh
OK="--set global.registry=example.azurecr.io --set-string global.tag=dev --set-string postgres.password=dev"
helm template bernstein charts/bernstein $OK \
  | yq -o=json -I0 '.spec | (.template.spec // .jobTemplate.spec.template.spec) | select(. != null) | (.containers + (.initContainers // []))[] | select((.resources.requests.cpu and .resources.requests.memory and .resources.limits.cpu and .resources.limits.memory) | not) | .name'
```

Prints nothing when every container has all four values. With `--set poll.resources.limits.cpu=null` it prints `"poll"`. The same command runs in CI (`ci.yml`, job `lint`).

On a cluster:

```sh
kubectl -n bernstein top pods
kubectl -n bernstein get pod -l app.kubernetes.io/component=poll -o jsonpath='{.items[0].status.qosClass}'
kubectl -n bernstein describe resourcequota compute
```
