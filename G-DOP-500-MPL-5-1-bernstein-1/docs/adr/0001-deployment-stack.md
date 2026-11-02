# ADR-0001: Deployment stack

- **Status:** Accepted
- **Date:** 2026-10-06
- **Deciders:** project team

## Context

The poll application (`poll`, `result`, `worker`, plus Redis and PostgreSQL) must run on a managed Kubernetes cluster in the cloud, be reproducible from the repository, and be deployed automatically. The constraints are:

- **Budget:** we run on Azure for Students credits, so idle cost matters and anything requiring a credit card or a paid plan is out.
- **Team:** small team, limited time; tools must be learnable and well documented.
- **Defense:** every choice, including the ones we rejected, will be questioned. Tools that make state and history visible (plan output, release history) help us explain what is deployed.

Five layers need a decision: the cloud and Kubernetes provider, how the cloud is provisioned, how the application is packaged, how traffic enters the cluster, and what runs CI/CD.

## Decision

| Layer                    | Choice                                       |
| ------------------------ | -------------------------------------------- |
| Kubernetes               | **AKS** (Azure Kubernetes Service)           |
| Infrastructure as code   | **Terraform** (`azurerm` provider)           |
| Application packaging    | **Helm** chart in `charts/bernstein`         |
| Ingress / traffic entry  | **Gateway API** implemented by **Traefik**   |
| CI/CD                    | **GitHub Actions**, OIDC federation to Azure |

### AKS

- Azure for Students gives credits without a credit card; the control plane on the Free tier costs nothing, so we only pay for nodes.
- Azure Container Registry integrates natively: the kubelet identity gets `AcrPull`, no image pull secrets to manage.
- It is the platform the evaluators use, so the defense environment matches ours.
- Workload identity and an OIDC issuer are built in, which the CI pipeline reuses.

### Terraform

- Declarative, with a reviewable `plan` before every change; state is stored remotely in Azure Storage (`infra/bootstrap`, `backend.tf`).
- Provider and Terraform versions are pinned, so runs are reproducible from the Nix dev shell.
- Skills transfer beyond Azure, and the same tool can manage non-Azure resources if needed.

### Helm

- The image tag is a template value, so CI deploys a given commit with `--set image.tag=<sha>` instead of editing manifests.
- `helm upgrade --install --atomic` rolls back automatically if the release does not become healthy.
- `helm history` / `helm rollback` give a release history we can show during the defense.

### Gateway API with Traefik

- Gateway API is the Kubernetes successor to `Ingress`, with role separation (`GatewayClass`, `Gateway`, `HTTPRoute`) and richer routing without vendor annotations.
- Traefik is a conformant, lightweight implementation installable with a single Helm chart.
- One cloud load balancer and public IP for both `poll` and `result`, routed by host or path.

### GitHub Actions

- The repository is already on GitHub; no extra service, account or runner to operate.
- OIDC federation to Azure means no long-lived client secret stored in the repository.
- Free minutes for the project's volume, and native integration with PR checks and branch protection.

## Alternatives

### Kubernetes provider

| Option       | Why rejected                                                                                              |
| ------------ | --------------------------------------------------------------------------------------------------------- |
| EKS (AWS)    | Control plane is billed hourly even when idle; no student credits comparable to Azure for Students.        |
| GKE (Google) | Requires a billing account with a card; Autopilot pricing harder to predict; differs from evaluator setup. |
| DigitalOcean | Cheap and simple, but no student credits on our accounts and not the platform used at the defense.        |
| Self-managed (k3s/kubeadm on VMs) | Not a managed cluster; we would own upgrades, etcd and the control plane for no grading benefit. |

### Infrastructure as code

| Option          | Why rejected                                                                                          |
| --------------- | ----------------------------------------------------------------------------------------------------- |
| Bicep           | Azure-only and the team has no experience with it; no advantage for the resources we need.           |
| `az` CLI scripts| Imperative: no plan, no drift detection, re-running is not idempotent without extra scripting.        |
| Pulumi          | Requires a general-purpose language runtime and a state backend choice; more moving parts than needed. |

### Application packaging

| Option         | Why rejected                                                                                              |
| -------------- | --------------------------------------------------------------------------------------------------------- |
| Kustomize      | Good for overlays, but no release concept: no history, no atomic rollback; image tag needs `kustomize edit`. |
| Raw manifests  | Image tag and environment values duplicated across files; rollback means re-applying an old commit by hand. |

### Traffic entry

| Option                     | Why rejected                                                                                          |
| -------------------------- | ----------------------------------------------------------------------------------------------------- |
| `Service type=LoadBalancer`| One public IP and load balancer per exposed service, which costs more and gives no host/path routing. |
| ingress-nginx              | Retired upstream in March 2026; starting a new project on it would mean an immediate migration.       |
| Application Gateway for Containers | Managed and Azure-native, but adds a billed Azure resource and ties routing to Azure.         |

### CI/CD

| Option            | Why rejected                                                                                       |
| ----------------- | -------------------------------------------------------------------------------------------------- |
| Azure Pipelines   | Separate Azure DevOps organisation to set up, while the code and reviews already live on GitHub.  |
| GitLab CI         | Would require mirroring the repository.                                                           |
| Argo CD / Flux    | GitOps controllers running in the cluster add cost and complexity; may be revisited in a later ADR. |

## Consequences

- **Lock-in:** AKS, ACR and the Azure budget/identity resources are Azure-specific. Helm, Gateway API and Terraform keep the application layer portable; moving clouds means rewriting `infra/terraform` only.
- **Cost:** nodes are the main cost; the cluster is stopped when unused (`make` targets, see `docs/cost.md`) and a subscription budget alerts by e-mail.
- **To maintain:** Terraform state backend, the Helm chart, Traefik and Gateway API CRD versions, and the federated credential used by GitHub Actions.
- **Revisit if:** student credits run out, the evaluation environment changes, or Gateway API support in Traefik regresses.
- Later significant choices (database hosting, secrets, observability, etc.) get their own ADRs, tracked in #37.
