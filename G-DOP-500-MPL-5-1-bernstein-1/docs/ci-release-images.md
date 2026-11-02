# CI: pushing images to ACR

`.github/workflows/release-images.yml` builds `poll`, `worker` and `result` on every push to `dev` or `main` and pushes them to the private registry `bernsteinacr.azurecr.io` (#12). It is step 2 of the subject: images in a private registry. The Azure side (identity, federated credentials, `AcrPush`) is in `infra/terraform/main.tf`.

## Tags

Each image gets two tags:

| Tag | Example | Moves? | Used by |
|---|---|---|---|
| Full commit SHA | `poll:3f9c1e2...` | never | deploys (`global.tag`, #23, #24) |
| Branch | `poll:dev`, `poll:main` | yes, to the latest push | humans, quick tests |

Deploys always use the SHA tag. With a moving tag like `latest`, the Deployment's pod template does not change when the image does, so Kubernetes starts no rollout; nodes that already pulled the old `latest` keep running it (`imagePullPolicy: IfNotPresent`), so replicas can run different code; and nobody can tell which commit is live. A SHA tag names exactly one build, and changing it in the Deployment is what triggers the rollout.

### Not pushing the same SHA twice

A release PR merges `dev` into `main`. With a merge commit the SHA is new and the images are built. With a fast-forward, `main` points to a commit that `dev` already built: the workflow first checks the registry

```sh
az acr manifest show-metadata -r "$ACR_NAME" -n "poll:$GITHUB_SHA"
```

and if the tag exists it does not rebuild, it only points `main` at the existing image (`docker buildx imagetools create`, which copies the manifest inside the registry). An existing SHA tag is therefore never overwritten by a different build: what was tested on `dev` is byte for byte what runs from `main`.

### Labels

`docker/metadata-action` adds the OCI labels, among them `org.opencontainers.image.revision` (commit SHA) and `org.opencontainers.image.source` (repository URL). `docker inspect` on any image shows where and from what it was built.

## Authentication: OIDC, no secret

```
GitHub Actions ──(OIDC token: repo:<org>@<org id>/<repo>@<repo id>:ref:refs/heads/dev)──> Entra ID
                                                                        │ matches a federated credential
                                                                        ▼ of bernstein-github-push
                                     short-lived Azure token <──────────┘
az acr login ──> bernsteinacr (AcrPush)
```

1. `permissions: id-token: write` lets the job ask GitHub for an OIDC token: a signed JWT saying which repository, branch and workflow is running.
2. `azure/login` sends it to Entra ID along with the identity's client ID. Entra checks the signature (issuer `https://token.actions.githubusercontent.com`) and that the token's `subject` matches one of the identity's federated credentials.
3. Entra returns an Azure token valid about an hour. `az acr login` exchanges it for a registry token.

GitHub stores four **repository variables** (not secrets), none of which grants access on its own:

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | `terraform output -raw github_push_client_id` |
| `AZURE_TENANT_ID` | `terraform output -raw tenant_id` |
| `AZURE_SUBSCRIPTION_ID` | `terraform output -raw subscription_id` |
| `ACR_NAME` | `bernsteinacr` |

Only the branches listed in `github_push_branches` (`dev`, `main`) have a federated credential. A workflow running on a pull request or a feature branch gets a token with another subject, which Entra rejects: a PR cannot push images, even by editing the workflow.

### The Terraform side

```hcl
resource "azurerm_user_assigned_identity" "github_push" { ... }

resource "azurerm_federated_identity_credential" "github_push" {
  for_each = toset(var.github_push_branches)

  name                      = "github-${each.value}"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_push.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:${var.github_repository}:ref:refs/heads/${each.value}"
}

resource "azurerm_role_assignment" "github_acr_push" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.github_push.principal_id
}
```

- **User-assigned managed identity rather than an app registration**: both accept federated credentials, but creating an app registration needs a directory permission that student tenants often deny. A managed identity is an Azure resource in our resource group: the subscription Owner can create it. It costs nothing.
- **`AcrPush` on the registry only**: push and pull images, nothing else. Not Contributor, not subscription-wide.
- The subject must match exactly. A job using a GitHub `environment:` gets `repo:<org>@<org id>/<repo>@<repo id>:environment:<name>` instead, and the login fails with `AADSTS70021: No matching federated identity record found`.
- **The subject contains the numeric IDs** of the organization and the repository. Our repository uses GitHub's *immutable subject* (`use_immutable_subject: true`), so the token says `repo:EpitechPGE3-2026@216019158/G-DOP-500-MPL-5-1-bernstein-1@1405326350:ref:refs/heads/dev`, not `repo:EpitechPGE3-2026/G-DOP-500-MPL-5-1-bernstein-1:...`. Terraform's `github_repository` holds the `owner@id/name@id` form. Until it did (#77), every login failed with:
  ```
  AADSTS700213: No matching federated identity record found for presented assertion subject
  'repo:EpitechPGE3-2026@216019158/G-DOP-500-MPL-5-1-bernstein-1@1405326350:ref:refs/heads/dev'
  ```
  The exact prefix GitHub uses is given by `gh api repos/{owner}/{repo}/actions/oidc/customization/sub` (`sub_claim_prefix`). The IDs are why this format is kept rather than switched back to names (`use_immutable_subject=false`): a renamed organization, or another repository later created under the same name, can never match our credentials.

### Setting it up

```sh
cd infra/terraform
terraform plan     # 1 identity, 2 federated credentials, 1 role assignment to add
terraform apply
gh variable set AZURE_CLIENT_ID       --body "$(terraform output -raw github_push_client_id)"
gh variable set AZURE_TENANT_ID       --body "$(terraform output -raw tenant_id)"
gh variable set AZURE_SUBSCRIPTION_ID --body "$(terraform output -raw subscription_id)"
gh variable set ACR_NAME              --body bernsteinacr
```

### Fallback without OIDC

If federated credentials are not usable, a service principal with only `AcrPush` on the registry, its JSON credentials stored in the `AZURE_CREDENTIALS` secret (`azure/login` with `creds:`). That secret is long-lived: rotate it (`az ad sp credential reset`) at least at the end of the project.

## Rejected alternatives

- **ACR admin user**: one shared static password with full rights on the registry. `admin_enabled = false` in Terraform.
- **`az acr build`** (build in Azure): no Docker needed in CI, but billed in ACR task minutes and loses the GitHub Actions layer cache shared with the PR builds (#11).

## Checks

```sh
az acr repository show-tags -n bernsteinacr --repository poll -o table   # SHA tags plus dev/main
docker buildx imagetools inspect bernsteinacr.azurecr.io/poll:dev       # same digest as the newest SHA tag
```
