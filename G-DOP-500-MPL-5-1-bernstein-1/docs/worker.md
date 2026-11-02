# Worker

What we ship for the worker, and why: the image (`poll-application/worker/Dockerfile`, #9) and the Deployment (`charts/bernstein/templates/worker/deployment.yaml`, #20).

## Role in the application

The worker is a Java program: it pops votes from the Redis list `votes` (`BLPOP`) and upserts them into PostgreSQL. It exits with code 1 on any Redis or database error and relies on Kubernetes to restart it. It also serves `/healthz` (always `ok`) and `/readyz` (checks Redis and PostgreSQL) on **port 80**, from a background `HttpServer` started before it connects to anything.

## What we ship

| Object | File | Issue |
|---|---|---|
| Container image | `poll-application/worker/Dockerfile` | #9 |
| Deployment | `charts/bernstein/templates/worker/deployment.yaml` | #20 |

There is no Service: nothing calls the worker, it only pulls from Redis. Only the kubelet reaches its health port, directly on the pod IP.

## The Deployment

```yaml
spec:
  replicas: {{ .Values.worker.replicas }}
  ...
      annotations:
        checksum/redis-secret: {{ include "bernstein.secretChecksum" (dict "context" $ "component" "redis") }}
        checksum/postgres-secret: {{ include "bernstein.secretChecksum" (dict "context" $ "component" "postgres") }}
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        sysctls:
          - name: net.ipv4.ip_unprivileged_port_start
            value: "0"
      containers:
        - name: worker
          ports:
            - name: health
              containerPort: 80
          env:
            {{- include "bernstein.env.redis" (dict "context" $) | nindent 12 }}
            {{- include "bernstein.env.postgres" (dict "context" $) | nindent 12 }}
```

### Rolling update

`maxUnavailable: 0`, `maxSurge: 1`, `minReadySeconds: 5` and `revisionHistoryLimit: 5`, as for poll ([poll.md](poll.md#rolling-update-without-errors)): a new worker (Redis and PostgreSQL reachable) is Ready before an old one stops, so votes keep being consumed. There is **no `preStop` sleep**: the worker has no Service, so nothing routes requests to it and there is no endpoint race to cover. `terminationGracePeriodSeconds: 40` is set only for consistency. Readiness stays at 5 s: nobody waits on a worker joining. See [ADR-0005](adr/0005-zero-downtime-rolling-updates.md).

### Two replicas

`BLPOP` hands each vote to exactly one of the consumers waiting on the list, and the insert is an upsert keyed by voter (`ON CONFLICT (id) DO UPDATE`), so two workers never conflict. Two replicas mean that a restart of one (crash, node drain, rolling update) does not stop the queue from draining, and that horizontal scaling of the consumers can be shown. The count is `worker.replicas`.

Rejected:

- **One replica**: simpler, but processing pauses for the whole restart, and there is nothing to scale.
- **KEDA `ScaledObject` on the Redis list length**: elegant autoscaling, but one more operator and its CRDs on the evaluator's fresh cluster. Possible bonus.

### Environment

The worker reads `REDIS_HOST`, `REDIS_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD`. They come from the helpers `bernstein.env.redis` and `bernstein.env.postgres` ([helm-helpers.md](helm-helpers.md#bernsteinenvredis-and-bernsteinenvpostgres)), shared with poll (Redis) and result (PostgreSQL), so a host, a port or a Secret key is written once. Both passwords come from Secrets, never from the Deployment. The Redis port is not configurable: the worker hardcodes 6379.

### Probes

| Probe | Path | Why |
|---|---|---|
| `startupProbe` | `/healthz`, every 2 s, 30 tries | The JVM needs a moment to start its health server. Liveness only begins after it succeeds. |
| `readinessProbe` | `/readyz`, every 5 s, timeout 4 s | Redis `PING` (1 s timeout) **and** `Connection.isValid(2)` on the database: up to 3 s when both are slow, hence the 4 s timeout. |
| `livenessProbe` | `/healthz` | Always `ok`. |

Liveness must not look at Redis or PostgreSQL: an outage of either would restart every worker for nothing. The worker already exits by itself on an error, and the readiness probe only reflects the dependencies.

### Resources

`requests: 100m / 256Mi`, `limits: 500m / 512Mi`. With `MaxRAMPercentage=75` ([JVM memory](#jvm-memory)) the heap tops out at 384 MiB, which is why the limit went from 256Mi to 512Mi: at 256Mi the heap was only 192 MiB, little room for the JVM's own overhead. The CPU limit also bounds the JVM's start-up burst (JIT compilation). QoS class **Burstable**. See [resources.md](resources.md) and [ADR-0006](adr/0006-cpu-limits.md). The numbers are starting points, to be checked with `kubectl top` under load.

### What was measured (kind)

Local kind cluster, two workers, votes sent through the poll Service:

| Check | Result |
|---|---|
| 20 votes from 20 voters | 20 rows in the database 0.5 s after the last vote |
| Worker deleted (`--force --grace-period=0`) during 300 votes | 319 of 320 rows: **one vote lost** |
| Worker deleted gracefully during 300 votes | 299 of 300 rows: **one vote lost** |
| PostgreSQL scaled to 0 | both workers `0/1` (NotReady) after 25 s, no restart |
| PostgreSQL back | workers stay NotReady until the next vote, then restart once and both are `1/1`; the votes are stored |

### Known limits

**A vote can be lost when a worker dies mid-vote.** `BLPOP` removes the vote from Redis before the insert. If the process is killed in between, the vote is gone. A graceful delete does not avoid it: the application has no shutdown hook, so `SIGTERM` stops the JVM at once. The loss is at most one vote per killed worker, and it only happens when a vote is being processed at that instant. The fix is `BLMOVE` to a processing list, acknowledged after the insert, which is an application change.

(When the *insert* fails, the worker puts the vote back with `LPUSH` before exiting, so a database outage does not lose votes.)

**After a database outage, recovery waits for the next vote.** The worker only notices a broken connection when it uses it. While PostgreSQL is down and no vote arrives, `isValid` fails, so the pods stay NotReady; once PostgreSQL is back they stay NotReady, since the dead connection is never replaced. The first vote then fails, is requeued, the process exits, and the restarted pod reconnects. No vote is lost in this sequence (4 of 4 stored). It cannot be solved with the liveness probe, which must stay on `/healthz`. It is harmless: no Service targets the worker, and with no votes there is nothing to process.

## The image

```dockerfile
FROM maven:3.9-eclipse-temurin-25@sha256:93b8a14e... AS build

WORKDIR /app

COPY pom.xml .
RUN mvn -q -B dependency:go-offline

COPY src ./src
RUN mvn -q -B -o package

FROM eclipse-temurin:25-jre@sha256:fcd7fd7b...

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75 -XX:+ExitOnOutOfMemoryError"

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=build /app/target/worker-jar-with-dependencies.jar ./worker.jar

USER 10001

EXPOSE 80

CMD ["java", "-jar", "worker.jar"]
```

### Two stages

The build stage has Maven and a full JDK (~500 MB); the runtime stage only has a JRE and the fat jar built by `maven-assembly-plugin` (`worker-jar-with-dependencies.jar`, all dependencies inside). Maven, the JDK and the source never reach the shipped image.

### Dependency layer

Docker reuses a layer only if everything copied before it is unchanged. The original Dockerfile copied `pom.xml` and `src` together, so any change to a `.java` file invalidated the layer that downloads dependencies, and every build downloaded all of Maven Central again.

Now `pom.xml` is copied alone and `mvn dependency:go-offline` downloads dependencies and plugins into the image's local repository (`~/.m2`). That layer only changes when `pom.xml` changes. `package` then runs with `-o` (offline): if `go-offline` missed something, the build fails instead of quietly downloading it again, so the cache stays honest.

Checked by rebuilding after appending a line to `Worker.java`:

```
Step 3/14 : COPY pom.xml .
 ---> Using cache
Step 4/14 : RUN mvn -q -B dependency:go-offline
 ---> Using cache
Step 5/14 : COPY src ./src
 ---> 6eb49b5ba231
Step 6/14 : RUN mvn -q -B -o package
```

### JVM memory

By default the JVM sizes its maximum heap at 25 % of the memory it sees. In a container it sees the cgroup limit, so with `limits.memory: 256Mi` the heap would be 64 MiB and most of the limit unused. Raising the heap too far has the opposite problem: heap plus metaspace, thread stacks and native memory goes over the limit and the kernel kills the container (`OOMKilled`) before the garbage collector reacts.

- `-XX:MaxRAMPercentage=75`: heap at 75 % of the limit, leaving 25 % for non-heap memory. With a 256 MiB limit:

  ```
  $ docker run -m 256m ... java -XX:+PrintFlagsFinal -version | grep MaxHeapSize
     size_t MaxHeapSize = 201326592   {product} {ergonomic}
  ```

  201326592 bytes = 192 MiB = 75 % of 256 MiB.
- `-XX:+ExitOnOutOfMemoryError`: on `OutOfMemoryError` the JVM exits instead of continuing in a broken state (threads dead, health server possibly still answering `ok`). Kubernetes then restarts the pod, which is the same recovery the worker already relies on for Redis and database errors.

`JAVA_TOOL_OPTIONS` is read by the JVM itself, so the flags apply without changing `CMD`, and can be overridden from the Deployment's `env` without rebuilding. The JVM prints `Picked up JAVA_TOOL_OPTIONS: ...` at startup, which shows the flags are active.

### Non-root user and port 80

The process runs as UID 10001 (`app`), a user created in the image with no home and no login shell, same as poll. A compromised worker is then not root in the container.

The worker listens on port 80, hardcoded in `Worker.java`, which we do not change. Linux only lets root bind ports below `net.ipv4.ip_unprivileged_port_start` (1024 by default). Without help, the non-root worker fails:

```
java.net.BindException: Permission denied
```

The fix is the namespaced sysctl `net.ipv4.ip_unprivileged_port_start=0`, set on the pod (`securityContext.sysctls`, in the Deployment). It is a "safe" sysctl in Kubernetes: allowed by default, it only affects the pod's own network namespace. Docker already sets it to 0 for containers, so `docker run` works locally without extra flags.

Rejected:

- **Running as root**: what we are removing.
- **`CAP_NET_BIND_SERVICE`** on the container: works, but adding a capability conflicts with dropping `ALL` capabilities in the restricted security context (#33).
- **Changing the port**: the application code is treated as fixed.

### Pinned base images

Both base images are pinned by digest (`tag@sha256:...`). The tag stays for readability; the digest decides what is pulled. A rebuild therefore gives the same base, and a base image update is a reviewed change (Dependabot PRs, #13) instead of something that happens silently.

To update a digest:

```sh
docker pull eclipse-temurin:25-jre
docker inspect --format '{{index .RepoDigests 0}}' eclipse-temurin:25-jre
```

### Rejected alternatives

- **Distroless Java image**: smaller and no shell, but no shell also means no `kubectl exec` debugging during the defense. Possible follow-up.
- **jlink custom runtime**: smallest image, but requires knowing every JDK module used by the dependencies. Too much for this project.

## Checks

```sh
docker build -t worker:test poll-application/worker
docker run --rm --entrypoint id worker:test
# uid=10001(app) gid=10001(app) groups=10001(app)
docker run -d --name wt -p 18080:80 worker:test
curl localhost:18080/healthz   # ok (200)
curl localhost:18080/readyz    # not ready (503): no Redis or PostgreSQL
docker rm -f wt
```
