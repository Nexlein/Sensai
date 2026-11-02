# Contributing to Bernstein

## Repository layout

| Path                  | Purpose                                                      |
| --------------------- | ------------------------------------------------------------ |
| `infra/terraform/`    | Azure resources (state backend, ACR, AKS, budget)            |
| `charts/bernstein/`   | Helm chart for the whole application                         |
| `scripts/`            | `deploy.sh`, `zero-downtime-check.sh`, helpers               |
| `docs/adr/`           | Architecture Decision Records                                |
| `docs/`               | Architecture, runbooks, defense Q&A                          |
| `poll-application/`   | Provided sources (only the Dockerfiles are modified)         |
| `.github/workflows/`  | CI/CD                                                        |

Put new files in the matching directory instead of creating a parallel one.

## Branch naming

`<type>/<short-kebab-description>`, without the issue number, e.g.
`feat/aks-cluster`, `fix/worker-healthcheck`, `chore/repo-layout`.

Types follow Conventional Commits: `feat`, `fix`, `chore`, `docs`, `ci`, `refactor`, `test`.

## Workflow

1. Open (or pick) an issue, then create its branch from `dev` and link it to the issue.
2. Open a pull request against `dev` that says `Closes #<issue>`.
3. At least one approval and passing CI are required before merging.
4. `dev` is merged into `main` through a pull request for releases.

`main` and `dev` are protected: direct pushes and force-pushes are rejected.
