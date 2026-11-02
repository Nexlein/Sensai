# infra/terraform

Azure resources: Terraform state backend, ACR, AKS, budget. Explained file by file in [docs/terraform.md](../../docs/terraform.md).

## Prerequisites

- Remote state storage created once with `infra/bootstrap` (#4).
- `az login` on the target subscription, with Owner rights (needed for the AcrPull and AcrPush role assignments).

## Usage

```sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # then set budget_contact_emails (required)
terraform init
terraform plan
terraform apply

az aks get-credentials \
  -g "$(terraform output -raw resource_group)" \
  -n "$(terraform output -raw aks_name)"
kubectl get nodes
```

`terraform destroy` removes the resource group, ACR and AKS; the state backend is not managed here and survives.

## What gets created

| Resource | Notes |
|---|---|
| Resource group `bernstein-rg` | `austriaeast` (see constraints below) |
| ACR `bernsteinacr` | Basic SKU, admin user disabled; pulls go through Entra identity |
| AKS `bernstein-aks` | Kubernetes 1.36 with patch auto-upgrade; 2 `Standard_DS2_v2_Promo` nodes (autoscaler on, min = max = 2) across zones 1-3; Azure CNI overlay + Cilium (NetworkPolicy enforced); OIDC issuer + workload identity; system-assigned managed identity |
| Role assignment | `AcrPull` for the kubelet identity on the ACR, so no `imagePullSecrets` |
| Managed identity | `bernstein-github-push`: `AcrPush` on the ACR, federated credentials for GitHub Actions on `dev` and `main` (OIDC, no secret) |
| Managed identity | `bernstein-github-deploy`: `Azure Kubernetes Service Cluster User Role` on the cluster, one federated credential for the GitHub environment `production` (see [docs/ci-deploy.md](../../docs/ci-deploy.md)) |
| Budget `bernstein-monthly` | Subscription scope, 60 €/month; e-mail at 50/80/100 % actual and 100 % forecasted |

Outputs: `resource_group`, `acr_login_server`, `aks_name`, `budget_id`, and `github_push_client_id`, `github_deploy_client_id`, `tenant_id`, `subscription_id` for the GitHub repository variables (see [docs/ci-release-images.md](../../docs/ci-release-images.md)).

## Azure for Students constraints

- A subscription policy only allows `switzerlandnorth`, `francecentral`, `italynorth`, `austriaeast` and `norwayeast`.
- B-series sizes are not offered to the subscription in any of these regions, and the sizes that are offered (v6/v7 families) have 0 vCPU quota.
- Every region is capped at 6 vCPU; `standardDSv2PromoFamily` has 4, which is exactly 2 × `Standard_DS2_v2_Promo`.
- So the pool is fixed at 2 nodes. A third node, a surge node during upgrades (`max_surge = 10%` rounds up to 1) or a pool rotation needs more quota; request it before upgrading the minor version or changing `node_vm_size`.
- azurerm v5 no longer registers resource providers by default, so `providers.tf` lists the ones this configuration needs.

Stop the cluster when unused to save credits: `make cluster-stop` / `make cluster-start` from the repo root. Prices and the expected total are in [`docs/cost.md`](../../docs/cost.md).
