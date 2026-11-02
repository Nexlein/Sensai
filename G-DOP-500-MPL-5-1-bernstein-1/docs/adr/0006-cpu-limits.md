# ADR-0006: Keep CPU limits on every workload

- **Status:** Accepted
- **Date:** 2026-10-13
- **Deciders:** TeddyBertrand

## Context

Every container needs memory limits (an unbounded leak takes the node) and requests (the scheduler and the autoscaler need them). CPU **limits** are debated: the kernel enforces them as a CFS quota, which throttles a container even when the node has idle CPU, and a popular recommendation is to set CPU requests only.

Forces here:

- The defense asks "how would you limit the processing power of Redis?". The answer is a CPU limit.
- Two small nodes (2 vCPU) shared by five workloads and an autoscaler: one pod in a busy loop (a JVM compiling, a heavy PostgreSQL query) can take a whole node.
- The apps are not latency-critical at the millisecond level; a vote page tolerates a few ms of throttling.

## Decision

Every container, hook Job included, sets CPU and memory requests and limits. Memory request equals memory limit for Redis and PostgreSQL. A namespace `LimitRange` and `ResourceQuota` back it up. Values in [resources.md](../resources.md).

## Alternatives

| Option | Why rejected |
| ------ | ------------ |
| Requests only, no CPU limits | Avoids throttling and uses idle CPU, valid for latency-sensitive services. Rejected for the noisy-neighbour risk on two small nodes and because it gives no answer to the Redis question. Revisit if load tests show throttling hurts (`container_cpu_cfs_throttled_periods_total`). |
| Guaranteed QoS everywhere (request = limit) | Reserves the full limit permanently: on 2 vCPU nodes this leaves no room for the autoscaler. |
| Cluster-wide policy engine (Kyverno, Gatekeeper) to require limits | Extra operator and CRDs on the evaluator's fresh cluster, rejected like the other operators. A CI check on the rendered chart plus a `LimitRange` do the job. |

## Consequences

- A pod over its CPU limit is slowed, not killed; one over its memory limit is OOM-killed and restarted.
- Limits must be sized with the JVM heap in mind (`MaxRAMPercentage=75`), or the worker is killed.
- A quota too tight refuses a rollout or autoscaling; it is sized for the autoscaler's maximum plus surge pods.
- Numbers need checking under load; throttling would show as high latency with low node CPU.
