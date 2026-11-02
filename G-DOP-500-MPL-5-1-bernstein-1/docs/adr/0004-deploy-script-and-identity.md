# ADR-0004: One deploy script shared by humans and CI, with a separate deploy identity

- **Status:** Accepted
- **Date:** 2026-10-13
- **Deciders:** project team

## Context

The defense asks us to deploy from scratch on a fresh cluster, possibly the evaluator's own AKS, and to show updates flowing from a commit to the cluster. Issues #23 and #24 left open how to deliver both.

- A manual sequence of commands fails on a typo under pressure.
- The evaluator's cluster was not created by our Terraform: it has no `AcrPull` assignment to our registry, no Gateway prerequisites, no namespace.
- CI needs to reach the cluster. The push identity already exists, but it holds credentials for the `dev` branch.
- `POSTGRES_PASSWORD` must never be in the repository.

## Decision

1. **`scripts/deploy.sh` is the only deployment path**, called by `make deploy` and by the `deploy` job of `release-images.yml` with `IMAGE_TAG=<sha>`. It is idempotent, checks its inputs before touching Azure, attaches the registry to the cluster if needed, installs the Gateway prerequisites only if absent, and runs `helm upgrade --install` with rollback on failure.
2. **The password reaches Helm through a process substitution**, never through the command line or a file.
3. **CI uses its own identity**, `bernstein-github-deploy`, with one federated credential bound to the GitHub environment `production` and `Azure Kubernetes Service Cluster User Role` on the cluster. The push identity is unchanged.
4. **Deploys are serialized** by a job-level concurrency group without cancellation.

Details: [deploy.md](../deploy.md), [ci-deploy.md](../ci-deploy.md), [terraform.md](../terraform.md).

## Alternatives

| Option | Why rejected |
| ------ | ------------ |
| README with the commands | Error-prone; not reproducible under defense pressure. |
| Argo CD / Flux (GitOps) | Adds a controller and a bootstrap step on the evaluator's fresh cluster, and makes "launch the deployment" indirect. Kept as a possible next step. |
| Terraform deploying the Helm release | Couples the application to our Azure state; unusable on a cluster we did not create. |
| Giving the push identity cluster access | Any push to `dev` could then reach the cluster. |
| A kubeconfig or service principal secret in GitHub | Long-lived, usable from anywhere, rotated by hand. |
| Separate scripts for CI and humans | Two paths to keep in sync; the one shown at the defense would not be the one tested by CI. |
| `--set-string postgres.password` | Visible in the process list while helm runs. |

## Consequences

- One path to test and to defend; the script grows an option (`SKIP_ACR_ATTACH`) for the one place where CI differs.
- The deploy identity is effectively cluster-admin until namespaced RBAC (#34), because the cluster has no Entra integration. The environment gate (approval, branch restriction) is the protection meanwhile.
- The first deployment on a cluster needs cluster-wide rights for the Gateway prerequisites.
- We revisit this if the cluster is shared with other applications (the Gateway would leave the chart), or if continuous reconciliation matters more than a direct, readable launch (GitOps).
