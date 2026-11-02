# Terraform

What `infra/` creates on Azure, file by file, and why it is written that way. Stack decision: [ADR-0001](adr/0001-deployment-stack.md). Short usage notes: [infra/terraform/README.md](../infra/terraform/README.md). Prices: [cost.md](cost.md).

## Primer

Terraform reads `.tf` files describing the Azure objects we want (the **desired state**), compares them with what it recorded last time (the **state**) and with what really exists, and computes a **plan**: the list of creations, changes and deletions that closes the gap. `terraform apply` executes that plan.

| Word | Meaning here |
|---|---|
| `resource "azurerm_x" "name"` | One Azure object. `azurerm_x.name` is how other blocks refer to it. |
| `data "..."` | Something that already exists and is only read (our subscription). |
| `variable` | An input with a type, a default and optionally a validation rule. |
| `output` | A value printed after `apply`, used by humans and by the GitHub repository variables. |
| provider | The plugin that talks to one platform's API (`azurerm` for Azure). |
| state | A JSON file mapping our blocks to real Azure IDs. Without it Terraform would try to create everything again. |

Plan symbols: `+` create, `~` change in place, `-/+` **replace** (delete then create, data lost), `-` delete.

Referring to another resource (`azurerm_resource_group.main.name`) is also how Terraform learns the **order**: the resource group is created before the registry because the registry reads its name.

## Layers and where Terraform stops

```
infra/bootstrap/bootstrap.sh   once, by hand   state storage (resource group, storage account, container)
infra/terraform/               terraform apply resource group, ACR, AKS, identities, roles, budget
charts/bernstein/, scripts/    helm            everything inside the cluster
```

Terraform never touches Kubernetes objects. The cluster boundary is deliberate: the evaluator may deploy on **their own** AKS, so everything inside the cluster must work without our Terraform ([deploy.md](deploy.md)).

## `infra/bootstrap/bootstrap.sh`: the state storage

Terraform needs somewhere to store its state *before* it can create anything, and that place cannot be created by the same Terraform (chicken and egg). So a script creates it once, with `az`:

| Object | Setting | Why |
|---|---|---|
| Resource group `bernstein-tfstate-rg` | `francecentral` | Outside the project group, so `terraform destroy` never deletes the state. |
| Storage account `bernsteintf<12 hex chars>` | name derived from the subscription id | Storage names are global and 3-24 lowercase alphanumerics; deriving it makes every run (and every teammate) pick the same name. |
| | `--allow-shared-key-access false` | No account key exists: access only through Entra identities. |
| | `--allow-blob-public-access false`, TLS 1.2 | Nothing public. |
| | versioning + 30 days soft delete | A corrupted or deleted state blob can be restored. |
| Container `tfstate` | private | Holds `bernstein.tfstate`. |
| Roles | `Storage Blob Data Contributor` for you and teammates, `Contributor` on the subscription for teammates | Reading and writing the blob, and creating resources. |

The script checks before every creation, so it can be run again. It prints the exact `terraform init` command for teammates.

Why a remote state: the state of the cluster contains its **admin kubeconfig**, and a local `terraform.tfstate` on one laptop would block the rest of the team. Blob storage gives a lock (`state blob is already locked` while someone applies), history and access control.

## `infra/terraform/`, file by file

### `versions.tf`

```hcl
terraform {
  required_version = "~> 1.15"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 5.8" }
  }
}
```

`~> 1.15` means `>= 1.15, < 2.0`. Pinning keeps two teammates from planning with different engines. `.terraform.lock.hcl` (committed) pins the exact provider build and its checksums on top.

### `backend.tf`

```hcl
backend "azurerm" {
  resource_group_name = "bernstein-tfstate-rg"
  container_name      = "tfstate"
  key                 = "bernstein.tfstate"
  use_cli             = true
  use_azuread_auth    = true
}
```

`storage_account_name` is left out because it depends on the subscription: it is passed at init (`terraform init -backend-config="storage_account_name=..."`). Forgetting it gives `lookup .blob.core.windows.net: no such host`: the host name is built from an empty account name. `use_azuread_auth` + `use_cli` authenticate with the `az login` session, since the account has no key.

### `providers.tf`

```hcl
provider "azurerm" {
  features {}
  use_cli = true
  resource_providers_to_register = [ "Microsoft.Compute", "Microsoft.ContainerRegistry", ... ]
}
```

- `features {}` is mandatory (empty) in azurerm.
- `use_cli`: no client secret anywhere, the plan runs as the person logged in.
- Resource providers: a fresh subscription has almost none registered, and the first call fails with `409 MissingSubscriptionRegistration`. azurerm v5 no longer registers them by default, so the list is explicit. A resource from a new namespace (for example `Microsoft.Storage`) must be added here.

### `variables.tf`

Every tunable value, with a type and a description. All have a default **except** `budget_contact_emails`, so an alert can never go to a placeholder address (a validation rejects an empty list). `acr_name` and `budget_start_date` carry validations: an ACR name must be 5-50 alphanumerics, and a budget must start on the first of a month. `terraform.tfvars.example` lists every default; copy it to the gitignored `terraform.tfvars` to override.

| Variable | Default | Note |
|---|---|---|
| `location` | `austriaeast` | Region policy, see [constraints](#azure-for-students-constraints). Changing it **replaces** everything. |
| `node_vm_size` | `Standard_DS2_v2_Promo` | The only size with quota. |
| `node_min_count` / `node_max_count` | 2 / 2 | 4 vCPU quota = 2 nodes. |
| `kubernetes_version` | `1.36` | Minor only; patches come from the auto-upgrade channel. |
| `github_repository` | the course repository | Part of every OIDC subject. |
| `github_push_branches` | `dev`, `main` | One federated credential per branch. |
| `github_deploy_environment` | `production` | GitHub environment allowed to deploy. |

### `main.tf`

Dependency graph (arrows: "is read by"):

```
resource_group ─┬─► container_registry ─┬─► role_assignment aks_acr_pull  (also needs the cluster)
                ├─► kubernetes_cluster ─┤
                ├─► identity github_push   ─► federated credentials (dev, main) + AcrPush on the registry
                └─► identity github_deploy ─► federated credential (environment) + Cluster User on the cluster
subscription (data) ─► budget
```

#### Resource group and registry

```hcl
resource "azurerm_container_registry" "main" {
  sku           = "Basic"
  admin_enabled = false
  ...
}
```

Basic SKU (the cheapest, enough for three small images). `admin_enabled = false` removes the shared admin password: only Entra identities can pull or push.

#### The cluster

| Setting | Why |
|---|---|
| `kubernetes_version = "1.36"`, `automatic_upgrade_channel = "patch"` | Security patches arrive without a decision from us; minor upgrades stay manual because a surge node does not fit the quota. |
| `default_node_pool` `system`, autoscaler on, min = max = 2 | `min_count` = `max_count` keeps the count fixed at what the quota allows while still letting the autoscaler own the number. Do **not** set `node_count`: the autoscaler owns it and the plan would show drift. |
| `zones = ["1","2","3"]` | Nodes spread over zones; `managed-csi` disks are then zone-redundant. |
| `temporary_name_for_rotation = "systemtmp"` | Required by azurerm to change pool properties in place; the rotation needs a temporary pool, i.e. extra quota. |
| `upgrade_settings.max_surge = "10%"` | The Azure default, written down so the plan shows no drift. 10 % of 2 nodes rounds up to 1 surge node. |
| `node_provisioning_profile { mode = "Manual" }` | Required by azurerm v5 (the alternative is node auto-provisioning, which we do not use). |
| `network_profile`: Azure CNI overlay, Cilium data plane and policy | Pods get overlay IPs (no VNet address exhaustion) and `NetworkPolicy` objects are **enforced** (a policy is not just stored and ignored). |
| `oidc_issuer_enabled`, `workload_identity_enabled` | Free; allow pods to use Azure identities later without secrets. |
| `identity { type = "SystemAssigned" }` | The control plane gets its own identity; no service principal to rotate. |

No paid tier is set, so the control plane is on the free tier: only nodes are billed (ADR-0001).

AKS also creates a second resource group `MC_bernstein-rg_bernstein-aks_austriaeast` holding the VM scale set, VNet, load balancer and the **kubelet identity**. AKS owns it: never edit it by hand or import it.

#### AcrPull

```hcl
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}
```

The **kubelet** (the agent on each node) pulls images, so it is the kubelet identity, not the cluster identity, that needs `AcrPull`. With it, pods pull `bernsteinacr.azurecr.io/...` with no `imagePullSecrets`. `skip_service_principal_aad_check` avoids a race: a just-created identity is not yet visible in Entra and the assignment would fail. On a cluster Terraform did not create, `scripts/deploy.sh` does the equivalent with `az aks update --attach-acr`.

#### Budget

Scope is the **subscription**, on purpose: the expensive resources live in the `MC_` group, and a budget on `bernstein-rg` would miss them. E-mails at 50, 80 and 100 % of the actual spend, plus 100 % forecasted. Budget alerts lag spend by up to 24 h: they warn, they do not cap.

#### GitHub identities

Two user-assigned managed identities, so the rights are split by what a workflow does:

| Identity | Federated credential subject | Role | Used by |
|---|---|---|---|
| `bernstein-github-push` | `repo:<repo>:ref:refs/heads/dev` and `.../main` | `AcrPush` on the registry | `image` job: build and push |
| `bernstein-github-deploy` | `repo:<repo>:environment:production` | `Azure Kubernetes Service Cluster User Role` on the cluster | `deploy` job: `helm upgrade` |

`<repo>` is `var.github_repository` in GitHub's immutable subject form, `owner@<owner id>/name@<repo id>` ([ci-release-images.md](ci-release-images.md#authentication-oidc-no-secret)).

Why two: a workflow on `dev` can push images (it has to), but must not be able to reach the cluster. With a single identity, any branch with a credential would also get cluster access. The deploy credential only matches jobs that declare `environment: production`, so GitHub's environment rules (approval, allowed branches) decide who can deploy.

Why managed identities and not an app registration: both accept federated credentials, but creating an app registration needs a directory permission that student tenants often refuse. How the login works and how to set the repository variables: [ci-release-images.md](ci-release-images.md) and [ci-deploy.md](ci-deploy.md).

#### Backup storage and identity

For the PostgreSQL backup CronJob ([postgres.md](postgres.md#backups)):

| Resource | Role |
|---|---|
| `azurerm_storage_account.backup` | `bernsteinbk<first 12 hex chars of the subscription id>` (names are global, so it is derived like the state account), Standard LRS, TLS 1.2, no public blobs, **`shared_access_key_enabled = false`**: no key exists, only Entra tokens work. |
| `azurerm_storage_container.backup` | `postgres-backups`, private. Created through the account's resource ID (ARM), because with shared keys disabled a data-plane call from Terraform would need extra provider settings. |
| `azurerm_storage_management_policy.backup` | Lifecycle rule: delete blobs 7 days (`backup_retention_days`) after their last modification. |
| `azurerm_user_assigned_identity.postgres_backup` | The identity the backup pod acts as. |
| `azurerm_federated_identity_credential.postgres_backup` | Issuer = the cluster's OIDC issuer URL, subject `system:serviceaccount:bernstein:postgres-backup`. Only a pod running as that ServiceAccount can exchange its Kubernetes token for an Azure token. |
| `azurerm_role_assignment.postgres_backup_blob` | `Storage Blob Data Contributor`, scoped to the container only (not the account). |

This needs the AKS OIDC issuer and workload identity, already enabled on the cluster, and `Microsoft.Storage` in `resource_providers_to_register` (otherwise `409 MissingSubscriptionRegistration`). A cluster not created by this Terraform needs the same pieces by hand; the chart keeps the CronJob off (`postgres.backup.enabled: false`) so the evaluator's deployment does not depend on them.

### `outputs.tf`

`backup_storage_account`, `backup_container` and `backup_client_id` feed the chart values `postgres.backup.*`. `resource_group`, `acr_login_server`, `aks_name`, `budget_id` for humans; `github_push_client_id`, `github_deploy_client_id`, `tenant_id`, `subscription_id` become repository variables (none of them is a secret: an identity id grants nothing without a matching OIDC token).

## Azure for Students constraints

These explain choices that look arbitrary.

- **Region policy.** Only `switzerlandnorth`, `francecentral`, `italynorth`, `austriaeast`, `norwayeast` are allowed. Elsewhere: `403 RequestDisallowedByAzure`. `az vm list-skus` ignores policies; check with `az policy assignment list`.
- **VM sizes and quota.** B-series is `NotAvailableForSubscription` in every allowed region and the v6/v7 families have 0 vCPU quota. Each region is capped at 6 vCPU. The only working size is `Standard_DS2_v2_Promo` in `austriaeast` (4 vCPU = 2 nodes). `az vm list-usage -l <region>` shows quotas (`limit` is a string).
- **Consequence.** No third node. A minor Kubernetes upgrade (surge node) and a `node_vm_size` change (temporary pool) both exceed the quota: request an increase first.

## Day-to-day

```sh
az login
cd infra/terraform
terraform init -backend-config="storage_account_name=bernsteintf<12 hex chars>"
terraform fmt -check && terraform validate      # also in CI, no Azure access needed (init -backend=false)
terraform plan                                  # read it
terraform apply
```

Rules that come from the traps above:

- **Read the plan before applying.** Changing `location`, `acr_name` or the resource group name shows `-/+`; replacing the resource group deletes everything in it, including the PV disks.
- Never commit `terraform.tfvars`, `*.tfstate`, `.terraform/`. Do commit `.terraform.lock.hcl`.
- The state holds the cluster admin kubeconfig: never copy it out of the backend.
- No secret in a variable. Access is managed identities and RBAC.
- **Stale lock** after an interrupted run: check `pgrep -af terraform`, then `terraform force-unlock <ID>`. A resource that exists in Azure but not in the state is `terraform import`ed, not deleted.
- Never `terraform destroy` to save money: the PV data is lost and recreation takes about 15 minutes. Use `make cluster-stop` ([cost.md](cost.md)).

## Rejected alternatives

| Option | Why not |
|---|---|
| Bicep / ARM templates | Azure-only, and Terraform was chosen in ADR-0001 for its reviewable `plan` and its transferable skills. |
| Pulumi, Crossplane | Another runtime (or an operator in the cluster) for the same result. |
| `az` scripts only | Not declarative: no diff, no drift detection. We keep `az` for the one-off bootstrap only. |
| Local state | Blocks the team and puts the admin kubeconfig on a laptop. |
| Terraform also managing Helm releases or Kubernetes objects | Ties the application to our Terraform; the evaluator's cluster would not have it. |
| Managed PostgreSQL / Azure Cache for Redis / Key Vault | Paid, and absent on the evaluator's cluster ([cost.md](cost.md), issues #15-#17). |
