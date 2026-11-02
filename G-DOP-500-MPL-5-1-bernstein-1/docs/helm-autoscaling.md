# Autoscaling poll and result

The subject asks for a deployment that is *scalable*, not just working. A fixed replica count wastes credits when idle and collapses under a burst of votes. The chart therefore ships a **HorizontalPodAutoscaler** (HPA) for poll, and for result once it can scale out. This document explains what an HPA is, what the chart renders, the traps, and what was rejected.

## What an HPA is

An HPA is a control loop built into Kubernetes. Every 15 seconds it reads a metric for the pods of a Deployment, computes the replica count that brings the metric to its target, and writes that count into the Deployment's `replicas`. The formula:

```text
desired = ceil( current replicas × current metric / target metric )
```

With 2 pods averaging 140 % of their CPU request and a target of 70 %, `desired = ceil(2 × 140 / 70) = 4`. The result is clamped to `[minReplicas, maxReplicas]`.

The metric comes from **metrics-server**, a small component that AKS installs by default. A plain kind cluster has none: the HPA then reports `<unknown>/70%` and never acts. That is why the demo runs on AKS.

## What the chart deploys

`templates/poll/hpa.yaml` and `templates/result/hpa.yaml` are one line each, calling the helper `bernstein.hpa` ([helm-helpers.md](helm-helpers.md#bernsteinhpa)):

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: {name: poll}
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: poll}
  minReplicas: 2
  maxReplicas: 5
  metrics:
    - type: Resource
      resource: {name: cpu, target: {type: Utilization, averageUtilization: 70}}
  behavior:
    scaleDown: {stabilizationWindowSeconds: 120}
```

Values (`poll.autoscaling`, same keys under `result.autoscaling`, checked by `values.schema.json`):

| Key | Default | Meaning |
|---|---|---|
| `enabled` | poll `true`, result `false` | Whether the HPA is rendered. |
| `minReplicas` | 2 | Floor. Two pods let one be lost or rolled without downtime ([ADR-0005](adr/0005-zero-downtime-rolling-updates.md)). |
| `maxReplicas` | 5 | Ceiling. `fail` at render time if below `minReplicas`. |
| `targetCPUUtilizationPercentage` | 70 | Average CPU as a percentage of the **request**. |
| `scaleDownStabilizationSeconds` | 120 | How long the recommended count must stay lower before pods are removed. |

### CPU utilisation is relative to the request

`averageUtilization: 70` does not mean 70 % of a core or of the limit: it is 70 % of `requests.cpu`. For poll (`50m`), the target is 35m per pod. This is why the requests had to be set first ([resources.md](resources.md)): without a request the HPA cannot compute a percentage and reports `<unknown>`. It also means the request is the lever: a higher request makes the HPA scale later.

### The scale-down window

Scaling up is fast (the default policy may double the count every 15 s). Scaling down is slowed by `stabilizationWindowSeconds: 120`: the HPA looks at the highest count it recommended during the last 2 minutes and keeps it. A brief dip in the load therefore does not remove pods that would be recreated seconds later; every flap would cost a pod start, a readiness wait and a `preStop` sleep.

## The Deployment must not set `replicas`

```yaml
  {{- if not .Values.poll.autoscaling.enabled }}
  replicas: {{ .Values.poll.replicas }}
  {{- end }}
```

The HPA writes `replicas` on the live Deployment. If the manifest also said `replicas: 2`, every `helm upgrade` would put the count back to 2 in the middle of a load peak. With the field absent, Helm leaves the count to the HPA. `poll.replicas` is ignored while the autoscaler is on.

**Trap:** upgrading a release that was installed *before* the autoscaler existed (so with `replicas: 2` in its manifest) drops the field, and the Deployment falls back to the API default of 1 until the HPA raises it to `minReplicas`. A fresh install never has the problem. Run the first such upgrade outside the demo.

## Why result is off

result's Socket.IO opens a session on one pod and the next request must reach the same pod, otherwise the browser gets "Session ID unknown" ([result.md](result.md)). More than one pod therefore needs sticky sessions at the Gateway (#26). Until then `result.autoscaling.enabled` is `false` and `result.replicas` is `1`. After #26: `--set result.autoscaling.enabled=true`. Its PodDisruptionBudget then appears by itself ([helm-availability.md](helm-availability.md)).

## Room on the nodes

Five poll pods request 250m CPU and 640Mi in total, so the two nodes hold the maximum (plus five result pods, if enabled, and one surge pod during a rollout) without a new node. The quota of the namespace is sized for it ([resources.md](resources.md#templatesnamespaceresourcequotayaml)). The **cluster autoscaler** (#5) adds nodes when pods are Pending; with the vCPU quota of the subscription (2 nodes, no surge node, see `infra/terraform/CLAUDE.md`) it cannot, and the demo does not depend on it.

## Verifying

```sh
helm template bernstein charts/bernstein $OK -s templates/poll/hpa.yaml
helm template bernstein charts/bernstein $OK -s templates/poll/deployment.yaml | grep replicas   # nothing
helm template bernstein charts/bernstein $OK --set poll.autoscaling.maxReplicas=1
# Error: ... values: poll.autoscaling.maxReplicas (1) is below minReplicas (2)
```

On AKS, the demo for the defense:

```sh
hey -z 60s -c 50 http://poll.<domain>/          # load
kubectl -n bernstein get hpa poll -w            # TARGETS rises, REPLICAS grows to 5
kubectl -n bernstein top pods -l app.kubernetes.io/component=poll
# stop the load: REPLICAS returns to 2 about two minutes later
helm upgrade ...                                # REPLICAS unchanged by the upgrade
```

**Not run yet.** It needs the AKS cluster and the load tool of #27, and belongs to the sprint-end test session. The rendering and the validation above are checked.

## Rejected

| Option | Why rejected |
|---|---|
| VPA (Vertical Pod Autoscaler) | Adjusts the CPU request that the HPA computes its percentage from: the two fight. It is also an add-on to install. |
| KEDA on the Redis list length for the worker | A better signal for a queue consumer, but one more operator and its CRDs on the evaluator's cluster. A possible bonus, not needed: two workers keep up with the vote rate. |
| Scaling on requests per second | Needs a metrics pipeline (Prometheus adapter) that is not on the cluster. |
| Memory as the metric | gunicorn and Node hold their memory after a peak, so it does not fall back and the count would never shrink. |
| Fixed `replicas` only | Wastes credits at idle or collapses under a burst; the issue's whole point. |
