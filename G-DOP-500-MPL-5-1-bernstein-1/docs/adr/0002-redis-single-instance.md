# ADR-0002: Redis as a single persistent instance

- **Status:** Accepted
- **Date:** 2026-10-13
- **Deciders:** project team

## Context

Redis sits between poll and the worker: poll pushes each vote onto the list `votes`, the worker pops it and writes it to PostgreSQL. Votes spend a fraction of a second in Redis, unless the worker is down, in which case they wait there. Constraints:

- **The application is fixed.** poll (`redis-py`) and the worker (Jedis) take a plain host; the worker hardcodes port 6379. Neither speaks Sentinel or Cluster.
- **Budget and time.** Every extra pod or paid service comes out of the student credits ([cost.md](../cost.md)), and the deployment must work on the evaluator's own fresh cluster.
- **Failure behaviour is already covered.** poll's `/readyz` pings Redis, so while Redis is down visitors get a 503 and no traffic reaches poll; the worker exits on any Redis error and Kubernetes restarts it.

## Decision

Run **one Redis 8 pod** as a StatefulSet with an append-only file on a persistent disk (`appendonly yes`, `appendfsync everysec`), a password (`requirepass`), and `maxmemory` below the container's memory limit with `noeviction`. Details in [redis.md](../redis.md).

- A crash or restart loses at most about a second of votes, and queued votes survive a pod deletion.
- When memory is full, Redis refuses new votes (poll shows an error) instead of dropping queued ones.

## Alternatives

| Option | Why rejected |
| ------ | ------------ |
| Redis Sentinel | 3 Redis pods (or 2 + sentinels) and a client that asks the sentinels for the primary. poll and the worker use a plain host, so failover would not reach them without changing the application. |
| Redis Cluster | Sharding for data that does not fit one server; a single list is one key, so it cannot be split. Same client problem. |
| Azure Cache for Redis | Billed whether or not the cluster runs, outside the cluster, and the evaluator's cluster would need network access to it. |
| Redis without persistence | A restart loses every queued vote, which is exactly the case where votes are queued (worker down). |
| `appendfsync always` | No loss on a crash, but one disk write per vote on a billed disk, for a window of one second. |
| Eviction policy of a cache (`allkeys-lru`) | The only key is the queue: evicting it silently drops votes. |

## Consequences

- Redis is a single point of failure: during a pod restart (seconds to a minute for the disk to reattach and the AOF to load) votes are refused with a 503, not lost.
- The disk is billed even when the cluster is stopped (E1 ZRS, 0.396 €/month).
- We would revisit this if votes must never be lost on a node failure (then: replication with an operator such as the Redis operator or Sentinel-aware clients) or if throughput outgrew one thread.
