# CI: deploying to AKS on merge to `main`

The `deploy` job of `.github/workflows/release-images.yml` (#24) runs `scripts/deploy.sh` ([deploy.md](deploy.md)) after the images of the commit are pushed. Merging to `main` therefore ends with new pods running the new SHA, with nobody's laptop involved.

## The job

```yaml
deploy:
  needs: image
  if: github.ref == 'refs/heads/main'
  environment: production
  concurrency:
    group: deploy-production
    cancel-in-progress: false
```

| Line | Effect |
|---|---|
| `needs: image` | Starts only when all three matrix jobs (poll, worker, result) succeeded: the SHA tags exist in ACR. |
| `if: ... main` | `dev` builds images but never deploys. |
| `environment: production` | The job belongs to a GitHub environment: optional manual approval, restriction to the `main` branch, environment secrets. It also changes the OIDC token subject (below). |
| `concurrency` | Two quick merges queue: the second deploy waits for the first. `cancel-in-progress: false` because cancelling a Helm run halfway can leave a release in `pending-upgrade`. GitHub keeps one running and one pending job per group; an older pending one is replaced by the newer, which is fine since the newest commit contains the older. |

The step passes `IMAGE_TAG=${{ github.sha }}` (the tag the `image` job pushed), `POSTGRES_PASSWORD` from a **secret** of the `production` environment, and cluster names from repository variables. `SKIP_ACR_ATTACH=1`: Terraform already granted `AcrPull`, and the deploy identity cannot read role assignments. `BACKUP_STORAGE_ACCOUNT`, `BACKUP_CONTAINER` and `BACKUP_CLIENT_ID` come from repository variables and enable the PostgreSQL backup CronJob; `deploy.sh` does not use `--reuse-values`, so each deploy on `main` sets them again. If one of the three variables is missing in GitHub, `deploy.sh` stops with an error instead of silently deploying without backups. `GITHUB_STEP_SUMMARY` receives the two URLs.

## Authentication

```
job (environment: production) ──OIDC token, subject repo:<org>@<org id>/<repo>@<repo id>:environment:production──> Entra ID
                                                   │ matches the credential of bernstein-github-deploy
az aks get-credentials  <── short-lived token <────┘
helm / kubectl ──> cluster
```

Same mechanism as for the push ([ci-release-images.md](ci-release-images.md)), with a different identity, `bernstein-github-deploy` ([terraform.md](terraform.md)): its only credential has the *environment* subject, so a workflow on `dev` or a pull request cannot obtain it. Its role, `Azure Kubernetes Service Cluster User Role`, lets it download the cluster kubeconfig.

Limit to know: our cluster has no Entra integration, so that kubeconfig carries the cluster's built-in credentials and the deploy identity is in practice **cluster-admin**. Narrowing it to one namespace is #34 (namespaced RBAC); until then the protection is the environment gate. This is the honest answer if asked at the defense.

## Setting it up

```sh
cd infra/terraform
terraform apply        # adds the identity, its credential and the role
gh variable set AZURE_DEPLOY_CLIENT_ID --body "$(terraform output -raw github_deploy_client_id)"
gh variable set AKS_RESOURCE_GROUP     --body "$(terraform output -raw resource_group)"
gh variable set AKS_NAME               --body "$(terraform output -raw aks_name)"
gh variable set BACKUP_STORAGE_ACCOUNT --body "$(terraform output -raw backup_storage_account)"
gh variable set BACKUP_CONTAINER       --body "$(terraform output -raw backup_container)"
gh variable set BACKUP_CLIENT_ID       --body "$(terraform output -raw backup_client_id)"
# AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID and ACR_NAME already exist (push workflow)

gh api -X PUT repos/<org>/<repo>/environments/production      # creates the environment
gh secret set POSTGRES_PASSWORD --env production              # asks for the value
```

Optional hardening in the repository settings: required reviewers on `production` (a manual approval before each deploy), and deployment branches limited to `main`.

The environment name must match `github_deploy_environment` in Terraform. If it does not, the login fails with `AADSTS70021: No matching federated identity record found`.

## First deployment

The Gateway API CRDs and Traefik are installed by `deploy.sh` when absent, which needs cluster-wide rights: today that works because the identity is effectively admin. Once #34 narrows it, run `make deploy` once from an administrator's machine and CI only upgrades the release.

## Rollback

`--rollback-on-failure` restores the previous revision when pods do not become Ready within 10 minutes, and `deploy.sh` exits non-zero, so the job turns red. `helm -n bernstein history bernstein` and `helm rollback` do it by hand.

## Rejected alternatives

- **Reusing the push identity**: it has credentials for `dev`, so any push to `dev` could reach the cluster.
- **A stored kubeconfig or service principal secret**: long-lived, valid from anywhere, and rotated by hand.
- **Deploying `dev` to a second namespace** (staging): doubles the pods on a 2-node cluster with no spare quota.
- **Argo CD / Flux** pulling from the repository: see [deploy.md](deploy.md).

## Not verified yet

Written without cluster access. To check at the end of the sprint on AKS: the OIDC login of the deploy identity, that the Cluster User kubeconfig lets `helm` create the namespace and CRDs, two quick merges queueing, and a failing rollout turning the job red.
