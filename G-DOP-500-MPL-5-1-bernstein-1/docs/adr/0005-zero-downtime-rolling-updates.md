# ADR-0005: Zero-downtime updates with a tuned rolling update and a preStop sleep

- **Status:** Accepted
- **Date:** 2026-10-13
- **Deciders:** TeddyBertrand

## Context

At the defense a service's source is changed and redeployed while the application is requested continuously: not one request may fail. The defaults of a Deployment are not enough:

- `maxUnavailable: 25 %` may remove a serving pod before its replacement is Ready (with 2 replicas it rounds down to 0, but this depends on the replica count, so it must be explicit);
- when a pod is deleted, the kubelet runs the `preStop` hook and sends SIGTERM **at the same time** as the endpoint controller removes the pod from the EndpointSlices. Traefik learns about it a moment later, and until then it still routes requests to a pod that is shutting down: connection refused or 502.

## Decision

A rolling update, tuned, on poll, result and worker; no new component.

- `strategy.rollingUpdate: {maxUnavailable: 0, maxSurge: 1}` and `minReadySeconds: 5`: the old pod is only removed after the new one has been Ready for 5 s.
- poll and result: `lifecycle.preStop: sleep 10` (native `sleep` action, Kubernetes ≥ 1.30). The pod keeps serving for 10 s while the endpoint removal propagates to Traefik, and only then receives SIGTERM.
- `terminationGracePeriodSeconds: 40`, above preStop (10 s) plus gunicorn's `graceful_timeout` (20 s). The kubelet counts the preStop time inside the grace period.
- `revisionHistoryLimit: 5` for a fast `helm rollback`.
- A change of a Secret rolls the pods through the `checksum/*-secret` annotations (see [helm-helpers.md](../helm-helpers.md)); the other settings are written in the pod template, so changing them changes the template.

### Timeline of an update (poll)

| t | Event |
|---|---|
| 0 | `helm upgrade` changes the pod template. A third pod (surge) is created. |
| ~5-15 s | The new pod passes its startup probe, then `/readyz`: it is added to the Service. |
| +5 s | `minReadySeconds` elapsed: the Deployment considers it available and may delete an old pod. |
| 0' | The old pod gets a deletion timestamp. In parallel: the endpoint controller removes it from the EndpointSlices, and the kubelet runs `preStop`. |
| 0'-10' | The pod still answers; Traefik stops sending it new requests once it sees the EndpointSlice update. |
| 10' | `sleep` ends, SIGTERM reaches gunicorn, which finishes in-flight requests (≤ 20 s) and exits. |
| ≤ 40' | Past this, SIGKILL. Never reached in practice. |

The cycle repeats for the second old pod.

## Alternatives

| Option | Why rejected |
| ------ | ------------ |
| Blue/green (two Deployments and a Service selector switch, or Argo Rollouts) | Also zero-downtime, with instant rollback, but double the resources (the budget has no headroom, see [cost.md](../cost.md)) and an extra controller or CRD to install on the evaluator's cluster. A rolling update is enough and native. |
| Readiness tuning without preStop | Readiness only decides when a pod *joins*. The race at shutdown (endpoint propagation vs SIGTERM) remains. |
| `preStop` with an `exec` of `sleep` | Needs a `sleep` binary in the image; the native action does not (the images are not ours to change beyond Dockerfiles, and result/poll are slim images). |
| preStop sleep on the worker | The worker has no Service: nothing routes to it, so there is no race to cover. It would only slow every rollout. |

## Consequences

- A rollout of poll takes about 30-40 s per pod because of `minReadySeconds` and the 10 s sleep. Accepted: the defense asks for no errors, not speed.
- poll keeps its readiness `periodSeconds: 10` (not 2): faster probing starves gunicorn threads when Redis is down, see [poll.md](../poll.md#the-trap-readiness-probes-can-starve-the-liveness-probe). A new poll pod therefore joins up to 10 s later than it could.
- With one result replica (Socket.IO needs sticky sessions before more, #26), the surge pod serves HTTP without a gap, but the open Socket.IO connections of the old pod drop and the browser reconnects.
- The rolling update needs room for one extra pod per Deployment: with 2 nodes this is within the current requests.
- Revisit if the autoscaler (#29) or the PodDisruptionBudgets (#28) interact badly with `maxSurge: 1`.
