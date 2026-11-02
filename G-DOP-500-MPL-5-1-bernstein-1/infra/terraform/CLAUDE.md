# infra/terraform

Terraform for the Azure resources of the project: resource group, ACR, AKS, the AcrPull role assignment linking them, the identity GitHub Actions uses to push images, and a subscription budget. The remote state backend is **not** managed here; it is created once by `infra/bootstrap/bootstrap.sh`.

## Layout

| File | Content |
|---|---|
| `versions.tf` | Terraform `~> 1.15`, azurerm `~> 5.8` |
| `backend.tf` | azurerm backend in `bernstein-tfstate-rg/tfstate/bernstein.tfstate`, Entra auth; `storage_account_name` is passed at init |
| `providers.tf` | azurerm provider, Azure CLI auth, resource providers to register |
| `variables.tf` | every input; all have defaults except `budget_contact_emails` |
| `main.tf` | all resources |
| `outputs.tf` | `resource_group`, `acr_login_server`, `aks_name`, `budget_id`, `github_push_client_id`, `github_deploy_client_id`, `tenant_id`, `subscription_id` |
| `terraform.tfvars.example` | defaults to copy into a gitignored `terraform.tfvars` |

## Commands

```sh
az login
cd infra/terraform
terraform init -backend-config="storage_account_name=bernsteintf<first 12 hex chars of the subscription id, no dashes>"
terraform fmt -check && terraform validate
terraform plan
terraform apply

az aks get-credentials -g "$(terraform output -raw resource_group)" -n "$(terraform output -raw aks_name)"
make -C ../.. cluster-stop    # always stop when not in use (student credits)
make -C ../.. cluster-start
```

`bootstrap.sh` prints the exact `init` command. Without `-backend-config`, init fails with `lookup .blob.core.windows.net: no such host`.

## Resources and dependency order

```
azurerm_resource_group.main ──► azurerm_container_registry.main ──┐
                            └─► azurerm_kubernetes_cluster.main ──┴─► azurerm_role_assignment.aks_acr_pull
```

- **ACR** `bernsteinacr`: Basic SKU, `admin_enabled = false`. No shared password; access is through Entra identities only.
- **AKS** `bernstein-aks`:
  - Kubernetes `1.36`, `automatic_upgrade_channel = "patch"`;
  - system pool `system`, autoscaler on with min = max = 2, zones 1-3, `temporary_name_for_rotation = "systemtmp"`, `upgrade_settings.max_surge = "10%"` (declared to match the Azure default and avoid drift);
  - `node_provisioning_profile { mode = "Manual" }`, required by azurerm v5;
  - Azure CNI overlay with Cilium data plane and Cilium network policy, so NetworkPolicies are enforced;
  - OIDC issuer and workload identity enabled; system-assigned managed identity.
- **AcrPull** for `kubelet_identity[0].object_id` on the ACR, so pods pull from `bernsteinacr.azurecr.io` without `imagePullSecrets`.
- **GitHub push identity** `bernstein-github-push`: user-assigned managed identity with `AcrPush` on the ACR and one federated credential per branch in `github_push_branches` (subject `repo:<github_repository>:ref:refs/heads/<branch>`). `github_repository` is in GitHub's immutable subject form `owner@<owner id>/name@<repo id>` (the repo has `use_immutable_subject: true`; check `sub_claim_prefix` with `gh api repos/{owner}/{repo}/actions/oidc/customization/sub`); the plain `owner/name` fails with `AADSTS700213`. `release-images.yml` logs in as it through OIDC; no secret exists. A user-assigned identity instead of an app registration because Epitech tenants may forbid app registrations. Explained in `docs/ci-release-images.md`.
- **GitHub deploy identity** `bernstein-github-deploy`: a second user-assigned identity, kept apart from the push one so that a workflow on `dev` (which can push images) cannot reach the cluster. One federated credential, subject `repo:<github_repository>:environment:<github_deploy_environment>` (default `production`), and `Azure Kubernetes Service Cluster User Role` on the AKS cluster. The `deploy` job of `release-images.yml` logs in as it. A job using `environment:` no longer has the `ref:refs/heads/...` subject, which is why this cannot reuse the push identity. Explained in `docs/ci-deploy.md`.
- **PostgreSQL backup storage**: account `bernsteinbk<12 hex of subscription id>` (Standard LRS, shared keys disabled), private container `postgres-backups`, lifecycle rule deleting blobs after 7 days, identity `bernstein-postgres-backup` federated with ServiceAccount `bernstein:postgres-backup` and `Storage Blob Data Contributor` on the container only. Used by the chart's `postgres-backup` CronJob. Explained in `docs/terraform.md`.
- **Budget** `bernstein-monthly`: subscription scope on purpose, since the costly resources sit in the `MC_` group and a budget on `bernstein-rg` would miss them. Thresholds 50/80/100 % actual + 100 % forecasted, max 5 notifications per budget. `start_date` must be the first of a month and not in a past month at creation. Costs are in `docs/cost.md`.
- AKS also creates `MC_bernstein-rg_bernstein-aks_austriaeast` (VM scale set, VNet, load balancer, kubelet identity). AKS owns it; never edit it by hand or import it into Terraform.

## Azure for Students constraints

These explain choices that would otherwise look arbitrary; check them before changing region or VM size.

- **Region policy:** "Allowed resource deployment regions" only allows `switzerlandnorth`, `francecentral`, `italynorth`, `austriaeast`, `norwayeast`. Anything else fails with `403 RequestDisallowedByAzure`. `az vm list-skus` does not take policies into account; check with `az policy assignment list`.
- **SKUs and quota:** B-series is `NotAvailableForSubscription` in every allowed region, and the offered v6/v7 families have 0 vCPU quota. Each region has a 6 vCPU total cap. The only working size found is `Standard_DS2_v2_Promo` in `austriaeast` (`standardDSv2PromoFamily`, 4 vCPU = 2 nodes). Check quotas with `az vm list-usage -l <region>` (`limit` is a string).
- **Consequences of the 4 vCPU limit:** there is no third node, and the surge node used by minor version upgrades and the temporary pool used by a `node_vm_size` change both exceed quota. Request a quota increase before either.
- **Resource providers:** azurerm v5 defaults `resource_provider_registrations` to `none`, and new subscriptions start with almost nothing registered (`409 MissingSubscriptionRegistration`). Any resource from a new namespace must be added to `resource_providers_to_register` in `providers.tf`.

## Rules

- Always read `terraform plan` before `apply`. Changing `location`, `acr_name` or the RG name **replaces** the resource (`-/+`), and replacing the RG deletes everything in it.
- Never commit `terraform.tfvars`, `*.tfstate` or `.terraform/`. Do commit `.terraform.lock.hcl`.
- The state contains the cluster admin kubeconfig: treat it as a secret and never copy it out of the backend.
- No secrets in variables; access goes through managed identities and RBAC.
- Do not set `node_count` on the pool: the autoscaler owns it and the plan would show drift.
- Stale lock after an interrupted run (`state blob is already locked`): first check that no `terraform` process is running (`pgrep -af terraform`), then `terraform force-unlock <ID>`. If a resource exists in Azure but not in state, `terraform import` it instead of deleting it.
