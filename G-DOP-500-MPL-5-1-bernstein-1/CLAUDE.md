# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Epitech DevOps project "Bernstein": deploy the provided poll application on a managed Kubernetes cluster (AKS, Azure for Students credits), reproducibly from this repository. It is graded at a defense: deploy from scratch on a **fresh cluster that may be the evaluator's own AKS, not one created by our Terraform**, show zero-downtime updates, and justify every choice, including rejected alternatives. The subject is `bernstein-project.pdf` at the repo root (gitignored, local only).

Work is tracked in GitHub issues (#2–#40). Each issue body holds the agreed design (proposed solution, rejected alternatives, acceptance criteria, dependencies): read it with `gh issue view <N>` before implementing, and follow it unless the user decides otherwise. Stack choices are fixed by [ADR-0001](docs/adr/0001-deployment-stack.md): AKS, Terraform, Helm, Gateway API with Traefik, GitHub Actions with OIDC.

## Architecture

```
poll --(RPUSH votes)--> Redis --(BLPOP votes)--> worker --(UPSERT)--> PostgreSQL <--(SELECT)-- result
```

`poll-application/` is provided code (see its README for ports, env vars, health endpoints). Treat the application code as fixed: only Dockerfiles and runtime config (e.g. `poll/gunicorn.conf.py`) are changed. App behaviors that drive the Kubernetes design:

- `schema.sql` must be applied before worker and result can work (Helm hook job, #16).
- worker and result `exit(1)` on any Redis/DB error and rely on Kubernetes restarts.
- `/readyz` checks dependencies, `/healthz` does not. Liveness must stay on `/healthz`, or a Redis/DB blip restarts every pod.
- result uses Socket.IO: more than one replica needs sticky sessions (#26).
- Service names are fixed (`redis`, `postgres`, `poll`, `result`), not release-prefixed: apps get hosts from env, and the worker hardcodes Redis port 6379.
- `POSTGRES_PASSWORD` must never be in the repository (subject requirement); it is supplied at deploy time (#17).

Layers, in deployment order:

1. `infra/bootstrap/bootstrap.sh`: run once, creates the Terraform state storage (`bernstein-tfstate-rg`, account `bernsteintf<first 12 hex chars of the subscription id>`).
2. `infra/terraform/`: resource group, ACR, AKS, AcrPull, GitHub push identity (OIDC, AcrPush), budget. **Read `infra/terraform/CLAUDE.md` before touching it**: region policy, vCPU quota (2 nodes, no surge node), and rules on plan/replace/state.
3. `charts/bernstein/`: one chart for the whole app, explained file by file in [docs/helm-chart.md](docs/helm-chart.md). Component manifests go in `templates/<component>/`, named like the component's key in `values.yaml`; every object uses the helpers with `(dict "context" $ "component" "<name>")`. Cluster-scoped prerequisites (Gateway API CRDs, Traefik) are not part of the chart.
4. `scripts/deploy.sh` (#23) and CI workflows (#11, #12, #24) are planned; today `.github/workflows/` only holds the project board automation.

Prefer in-cluster, operator-free solutions: paid Azure services (managed PostgreSQL, Azure Cache for Redis, Application Gateway, Key Vault) and extra operators/CRDs were rejected in the issues because of credits and because they would have to be installed on the evaluator's fresh cluster.

## Cost

All spend comes from student credits; [docs/cost.md](docs/cost.md) has the prices and the expected total. What follows from it:

- **The budget has almost no headroom.** With the stop routine the two-week estimate is ~56 € against the 60 € `bernstein-monthly` budget. About 15 extra hours of cluster uptime, or a few new always-billed items, trip the 100 % alert.
- **The two nodes are the only thing stopping saves**: 0.308 €/h together (~5 € per night left running, ~20 € per weekend). Everything else (OS disks, load balancer, public IPs, persistent disks, ACR, ≈ 31 € over the two weeks) is billed even when the cluster is stopped.
- `make cluster-start` starts billing: ask before starting the cluster. After any work that needed it, remind the user to run `make cluster-stop`. A stopped cluster keeps its workloads and PV disks, so nothing has to be redeployed after `cluster-start`.
- Never suggest `terraform destroy` or scaling the pool to 0 to save money: destroy loses the PV data and takes ~15 min to recreate, and a system pool cannot scale to 0.
- Budget alerts lag spend by up to 24 h; they do not confirm that a change is cheap.

Changes that add billed resources must update `docs/cost.md` (unit price table and both totals) in the same PR, and say so in the PR description:

- **Each `Service type=LoadBalancer`** adds a public IP (0.0044 €/h, billed while stopped). The design is a single Gateway entry point for both apps; do not add LoadBalancer Services. The load balancer price assumes ≤ 5 rules.
- **Each PVC** is an Azure managed disk billed at its provisioned tier, while stopped, and StatefulSet PVCs survive `helm uninstall`, so they keep billing until deleted. `docs/cost.md` counts two disks (PostgreSQL, Redis); backups (#31) add more.
- **Any new Azure resource or AKS add-on** is outside the current estimate.
- Prices come from the [Azure Retail Prices API](https://prices.azure.com/api/retail/prices): pay-as-you-go retail, EUR, excluding VAT, with the query date. `austriaeast` has no public DS2 v2 price, so the `francecentral` price is used.
- If the expected total goes above the budget, raise it with the user rather than silently changing `budget_amount`.

## Commands

Tools (`az`, `terraform`, `kubectl`, `helm`, `docker`, `gh`, `jq`) come from the Nix flake dev shell (`.envrc` is `use flake`). If they are not on `PATH`, prefix commands with `nix develop -c`.

```sh
# Terraform (details and backend init in infra/terraform/CLAUDE.md)
cd infra/terraform && terraform fmt -check && terraform validate
terraform init -backend=false      # enough for validate without Azure access

# Helm: global.registry and global.tag (schema) and postgres.password (template) are required, lint included
OK="--set global.registry=example.azurecr.io --set-string global.tag=dev --set-string postgres.password=dev"
helm lint --strict charts/bernstein $OK
helm template bernstein charts/bernstein $OK
helm template bernstein charts/bernstein $OK -s templates/redis/secret.yaml   # render one template
helm template bernstein charts/bernstein $OK | nix shell nixpkgs#kubeconform -c kubeconform -strict -summary -kubernetes-version 1.36.0

# Real behaviour without AKS: local kind cluster with its own kubeconfig (recipe in docs/helm-chart.md)
nix shell nixpkgs#kind -c kind create cluster --name bernstein-test --kubeconfig /tmp/bernstein-kind.kubeconfig

# Cluster power (from repo root; override RESOURCE_GROUP / AKS_NAME if needed)
make cluster-status
make cluster-start                  # also fetches kubeconfig, waits for nodes Ready
make cluster-stop
```

Always pass the image tag with `--set-string`: an all-digit short SHA passed with `--set` becomes a number and fails the schema. There is no test suite; checks are `terraform fmt/validate`, `helm lint`/`helm template`/`kubeconform`, and the issue's acceptance criteria, run on a local kind cluster when they need a cluster (always pass `--kubeconfig` so the user's current context, possibly AKS, is untouched; delete the cluster afterwards).

## Documentation

Every new piece of the deployment (chart templates and helpers, Terraform resources, scripts, workflows) and anything non-obvious gets an explanatory document in `docs/`, written for teammates who must understand it and defend it. The models are:

- [docs/helm-chart.md](docs/helm-chart.md): file by file, what it is, what the tool does with it, why it is written that way and what was rejected;
- [docs/helm-helpers.md](docs/helm-helpers.md): a primer of the syntax involved, then the code quoted and explained line by line, with real rendered output.

Rules:

- Each component (`poll`, `worker`, `result`, `redis`, `postgres`) has one document named after it (`docs/postgres.md`, `docs/redis.md`, ...) covering everything the chart deploys for it: create it with the component's first template, and extend it in every issue touching that component.
- Cross-cutting topics extend the area's existing document (chart-wide files and mechanisms in `helm-chart.md`, helpers in `helm-helpers.md`); a new topic gets `docs/<area>-<topic>.md`. Add every new document to the index in `docs/README.md`.
- Quote code instead of citing line numbers, show actual output (rendered YAML, error messages), explain the why (constraint, failure it prevents), and record the traps hit while building it with their exact error text.
- Write the document in the same PR as the change; a change that makes a document wrong fixes it in that PR.
- Directory READMEs (e.g. `charts/bernstein/README.md`) stay short: usage and reference. The explanation lives in `docs/`.

## Workflow and conventions

- Branch from `dev`, linked to its issue: `gh issue develop <N> --name <type>/<slug> --base dev` (the link moves the card on the project board). PRs target `dev` and say `Closes #<N>`; `main` only receives `dev` through release PRs. Both are protected.
- Commits: Conventional Commits with a scope, e.g. `feat(poll): ...`, `build(terraform): ...`, `docs(adr): ...`, `chore(nix): ...`.
- `CHANGELOG.md`: user-visible changes go under "Unreleased" (Keep a Changelog).
- ADRs: write one when a choice is made (copy `docs/adr/0000-template.md`, next number, add it to the index in `docs/adr/README.md`). An accepted ADR is never rewritten; a changed decision gets a new ADR that supersedes it.
- `.github/workflows/project-board.yml` and `.github/scripts/project-board.js` are managed by project-bootstrap: do not edit them by hand.
- New files go in the matching directory from `CONTRIBUTING.md` (`infra/`, `charts/`, `scripts/`, `docs/`), not in parallel ones.
- Create and change files with the Write and Edit tools, never with shell heredocs, `sed -i` or inline Python scripts: the user reviews each edit as a diff. Bash is for running commands (`helm`, `kubectl`, `git`, `gh`).
