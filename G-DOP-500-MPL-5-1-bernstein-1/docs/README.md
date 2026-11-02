# docs

Architecture, runbooks and defense Q&A. Documentation that only explains one directory stays next to it (see [Next to the code](#next-to-the-code)).

## Index

| Area | Document | Content |
|---|---|---|
| Decisions | [adr/](adr/README.md) | Architecture Decision Records: why each tool was chosen and what was rejected |
| Runbooks | [runbooks/restore.md](runbooks/restore.md) | Restore the PostgreSQL database from a Blob backup |
| Cost | [cost.md](cost.md) | Azure prices, expected total, budget alert, stop/start routine |
| Infrastructure | [terraform.md](terraform.md) | Terraform primer, the state bootstrap, every `.tf` file and resource, the two GitHub identities, Azure for Students constraints, rejected alternatives |
| Deploy | [deploy.md](deploy.md) | `scripts/deploy.sh` and `destroy.sh` step by step, required environment, idempotence, fresh evaluator cluster |
| CI | [ci-deploy.md](ci-deploy.md) | `deploy` job: environment, OIDC identity, sequential releases, rollback, GitHub setup |
| CI | [ci-pull-requests.md](ci-pull-requests.md) | Pull request workflow: lint, image builds, path filtering, required checks |
| CI | [ci-release-images.md](ci-release-images.md) | Push workflow: OIDC login to Azure, SHA tags in ACR, identity setup |
| CI | [ci-image-scanning.md](ci-image-scanning.md) | Trivy scan of pushed images, Security tab upload, Dependabot |
| Helm | [helm-chart.md](helm-chart.md) | Every file of `charts/bernstein`: what Helm does with it and why it is written that way; passwords in general; testing on a local cluster |
| Helm | [helm-helpers.md](helm-helpers.md) | What a helper is, Go template syntax, `_helpers.tpl` line by line |
| Components | [poll.md](poll.md) | Everything deployed for poll: Deployment, environment, port 80 as non-root, probes and why liveness ignores Redis, Service |
| Components | [result.md](result.md) | Everything deployed for result: Deployment, PostgreSQL environment, port 80 as non-root, probes and why liveness ignores PostgreSQL, one replica until sticky sessions, Service |
| Networking | [gateway.md](gateway.md) | Public entry point: Gateway API CRDs and Traefik install script, Gateway, host-based HTTPRoutes on nip.io, checks and traps |
| Kubernetes | [k8s-statefulset.md](k8s-statefulset.md) | What a StatefulSet is and why, its pieces (headless Service, volume templates, PVC), how PostgreSQL and Redis use it, lifecycle and traps |
| Helm | [helm-hooks.md](helm-hooks.md) | What a Helm hook is, its moments, weights and delete policies; every hook of the chart in run order |
| Testing | [zero-downtime-check.md](zero-downtime-check.md) | `zero-downtime-check.sh` (continuous requests during a rollout, error report, exit code) and the `make zdt-demo` defense scenario |
| Components | [postgres.md](postgres.md) | Everything deployed for PostgreSQL: StatefulSet, data disk and storage class, Services, password Secret |
| Components | [redis.md](redis.md) | Everything deployed for Redis: generated password, then StatefulSet and persistence |
| Components | [result.md](result.md) | The result image: tini as PID 1 for SIGTERM, non-root user, dependency layers |
| Components | [worker.md](worker.md) | The worker image (build layers, JVM memory flags, non-root user and port 80) and Deployment (replicas, probes, known limits) |
| Components | [redis.md](redis.md) | Everything deployed for Redis: generated password, StatefulSet, persistence, memory and CPU limits, Services |
| Testing | [testing/](testing/README.md) | Manual acceptance suite: static checks, deploy, functional, resilience and zero downtime, data and restore, operations; result sheet |
| Helm | [helm-autoscaling.md](helm-autoscaling.md) | The HorizontalPodAutoscaler of poll (and result later): how it computes the count, values, why `replicas` is omitted, demo, rejected options |
| Helm | [helm-availability.md](helm-availability.md) | PodDisruptionBudgets and pod spreading: what a node drain does to each component, why Redis and PostgreSQL have no PDB |
| Helm | [resources.md](resources.md) | Requests and limits of every workload, QoS classes, CFS quota and throttling, namespace LimitRange and ResourceQuota |

Planned: from-scratch deployment guide (#36), architecture and technical choices (#37), defense Q&A (#38).

## Next to the code

| File | Content |
|---|---|
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Repository layout, branch naming, pull request flow |
| [infra/terraform/README.md](../infra/terraform/README.md) | Provisioning the Azure resources, Azure for Students constraints |
| [charts/bernstein/README.md](../charts/bernstein/README.md) | Install command, values, how to write templates |
| [poll-application/README.md](../poll-application/README.md) | The provided application: services, ports, env vars, health endpoints |

## Adding a document

- **A component** (`poll`, `worker`, `result`, `redis`, `postgres`) has one document named after it, covering everything the chart deploys for it. It grows with each issue touching that component.
- **Any other topic**: one file in kebab-case, prefixed by its area (`helm-`, ...) so related documents sort together.

Add the document to the index above in the same pull request. ADRs follow their own process, described in [adr/README.md](adr/README.md).
