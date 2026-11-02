# Surviving a node drain: PodDisruptionBudgets and pod spreading

A typical defense question: "what happens if we `kubectl drain` this node?". A drain evicts every pod of a node at once. Cluster upgrades and the autoscaler's scale-down do the same. This document explains what the chart does so that poll, result and worker stay up, and what it deliberately does not do for Redis and PostgreSQL.

Two mechanisms work together:

| Mechanism | Question it answers | File |
|---|---|---|
| `topologySpreadConstraints` | Where do the pods of one component land? On different nodes, so a node does not hold all of them. | the three Deployments |
| `PodDisruptionBudget` (PDB) | How many may be evicted at the same time? Never the last one. | `templates/<component>/pdb.yaml` |

Spreading makes a drain *possible* without an outage (another pod is on another node); the PDB makes it *safe* (the drain waits for the evicted pod's replacement to be Ready before it evicts the next).

## `bernstein.topologySpread`

```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: ScheduleAnyway
    labelSelector:
      matchLabels: {app.kubernetes.io/name: bernstein, ..., app.kubernetes.io/component: poll}
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    ...
```

- `topologyKey` names the node label that defines a domain: one domain per node (`hostname`), one per availability zone (`zone`). The scheduler counts the component's pods per domain and keeps the difference between the fullest and the emptiest domain under `maxSkew: 1`.
- The selector is the component's selector labels, so poll pods are only counted against poll pods.
- **`ScheduleAnyway` makes it a preference.** When the rule cannot be met, the pod is still scheduled where it hurts least. The alternative, `DoNotSchedule`, leaves the pod Pending: with the autoscaler at 5 poll pods on 2 nodes, the 5th would never run. Hard pod anti-affinity has the same flaw and was rejected for it.
- The AKS node pool spans the zones of its region (`zones 1-3` in `infra/terraform/`), so the zone constraint is real there. On a cluster without zone labels (kind) the zone constraint has no effect and the scheduler ignores it.
- The helper returns a list beginning with a newline; the Deployments call it with `| trim | nindent 8`.

Spreading is applied when a pod is *scheduled*. It does not move running pods: after a drain, both poll pods may sit on the same node until the next rollout. That is acceptable for the defense scenario and is why the PDB, not the spreading, is the actual guarantee.

## `bernstein.pdb`

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: {name: poll}
spec:
  minAvailable: 1
  selector:
    matchLabels: {app.kubernetes.io/name: bernstein, ..., app.kubernetes.io/component: poll}
```

`kubectl drain` does not delete pods: it asks the API for an **eviction**, and the API refuses it if it would leave fewer than `minAvailable` ready pods. The drain then retries until the replacement of the first evicted pod is Ready and the second can go. With two poll pods on the drained node, one is evicted, rescheduled elsewhere, becomes Ready, then the other is evicted: poll always has a ready pod.

- **Rendered only when the component runs more than one pod.** The count is the autoscaler's `minReplicas` when it is enabled, else `replicas`. With a single pod (result until #26), `minAvailable: 1` would refuse every eviction and a drain would **hang forever**. result gets its PDB automatically the day its autoscaler is turned on.
- It applies to *voluntary* disruptions only (drain, upgrade, scale-down). A node that dies is not asked.
- `minAvailable: 1` and not `maxUnavailable: 1`: with the autoscaler at 5 pods, `minAvailable: 1` would allow 4 evictions at once. Accepted: the point is never to evict the last pod, and a higher number would block a drain when pods are unready.

## Redis and PostgreSQL: no PDB, on purpose

Both run as one pod with a ReadWriteOnce disk. A PDB with `maxUnavailable: 0` (or `minAvailable: 1` on a single pod) would make every drain hang: node maintenance and AKS upgrades could never finish. Not having one means a drain **does** interrupt them, briefly. What happens:

1. The drain evicts the pod. The StatefulSet creates the replacement on another node.
2. The Azure Disk detaches from the old node and attaches to the new one (the disk is zone-redundant, `managed-csi`, so it can follow the pod across zones).
3. PostgreSQL / Redis start on the existing data (crash-safe: PostgreSQL's `pg_wal` replay, Redis's append-only file).
4. In the meantime:
   - poll pods fail `/readyz` (Redis ping), so the gateway stops sending them traffic: visitors get a 503 until Redis is back;
   - worker and result exit(1) on the lost connection and Kubernetes restarts them with back-off; the votes stay queued in Redis, nothing is lost;
   - when the databases are back, `/readyz` passes again and the pods rejoin by themselves.

**Observed failover time: not measured yet.** It needs the AKS cluster (a drain moves a disk between nodes, which kind cannot reproduce) and is part of the sprint-end test session, with the drain run during the #27 load. The measured number goes here and in the Q&A (#38).

## Verifying

```sh
helm template bernstein charts/bernstein $OK -s templates/poll/pdb.yaml
helm template bernstein charts/bernstein $OK -s templates/result/pdb.yaml   # empty: one replica
kubectl -n bernstein get pdb                                   # ALLOWED DISRUPTIONS 1 with 2 ready pods
kubectl -n bernstein get pod -l app.kubernetes.io/component=poll -o wide   # NODE column: different nodes
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data
```

Checked so far: lint, `kubeconform` (21 resources), the rendered PDBs (poll and worker only, since result has one replica) and the rendered constraints. The drain with continuous load (#27) is not run yet.

## Rejected

| Option | Why |
|---|---|
| PDB `maxUnavailable: 0` on the databases | Blocks all node maintenance. |
| Hard pod anti-affinity / `DoNotSchedule` | Pods stay Pending when there are more pods than nodes. |
| A PDB with a fixed `minAvailable` value in `values.yaml` | One more knob without a use: 1 is what protects the service. |
| An HA PostgreSQL (operator) to avoid the short outage | Operator and CRDs to install on the evaluator's cluster, and extra pods against the credit budget ([ADR-0001](adr/0001-deployment-stack.md)). |
