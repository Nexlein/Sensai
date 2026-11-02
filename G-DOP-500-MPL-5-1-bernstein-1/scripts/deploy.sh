#!/usr/bin/env bash
# One-command deployment of Bernstein on an AKS cluster, from this repository.
# Idempotent: running it again with the same inputs changes nothing.
#
# Required environment:
#   POSTGRES_PASSWORD    password of the PostgreSQL user (never written to a file)
#   AKS_RESOURCE_GROUP   resource group of the cluster
#   AKS_NAME             name of the cluster
#   ACR_NAME             name of the container registry (without .azurecr.io)
#                        (created in AKS_RESOURCE_GROUP if it does not exist)
# Optional:
#   IMAGE_TAG            tag of images already in the registry; unset: build and push HEAD,
#                        plus the uncommitted changes of a service under its own tag
#   NAMESPACE            target namespace (default: bernstein)
#   SKIP_ACR_ATTACH=1    do not create the registry nor check/grant the cluster's pull access
#                        (CI: the identity cannot read role assignments, Terraform did it)
#   BACKUP_STORAGE_ACCOUNT, BACKUP_CONTAINER, BACKUP_CLIENT_ID
#                        all three: enable the PostgreSQL backup CronJob (terraform outputs
#                        backup_storage_account, backup_container, backup_client_id);
#                        none: no backup; only some: error
#
# Prints the two URLs on stdout, progress on stderr. Explained in docs/deploy.md.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
namespace="${NAMESPACE:-bernstein}"
release="bernstein"

log() { echo ">> $*" >&2; }
die() { echo "error: $*" >&2; exit 1; }

# 1. Tools and inputs, before anything is touched.
tools=(az kubectl helm jq)
[ -n "${IMAGE_TAG:-}" ] || tools+=(docker git)
for tool in "${tools[@]}"; do
  command -v "${tool}" >/dev/null || die "${tool} is not installed (see CLAUDE.md: nix develop)"
done
if [ -z "${IMAGE_TAG:-}" ]; then
  docker buildx version >/dev/null 2>&1 \
    || die "docker buildx is not installed (plugin docker-buildx, see README.md)"
fi

for var in POSTGRES_PASSWORD AKS_RESOURCE_GROUP AKS_NAME ACR_NAME; do
  [ -n "${!var:-}" ] || die "${var} is not set (see docs/deploy.md)"
done

# Backups: all three variables or none. A partial set is a mistake (typo, missing CI
# variable), not a request to deploy without backups.
backup_vars=(BACKUP_STORAGE_ACCOUNT BACKUP_CONTAINER BACKUP_CLIENT_ID)
backup_set=0
for var in "${backup_vars[@]}"; do
  [ -z "${!var:-}" ] || backup_set=$((backup_set + 1))
done
case "${backup_set}" in
  0) backup=(--set postgres.backup.enabled=false) ;;
  3) backup=(--set postgres.backup.enabled=true
       --set-string "postgres.backup.storageAccount=${BACKUP_STORAGE_ACCOUNT}"
       --set-string "postgres.backup.container=${BACKUP_CONTAINER}"
       --set-string "postgres.backup.clientId=${BACKUP_CLIENT_ID}") ;;
  *) die "set all of ${backup_vars[*]} to enable backups, or none (see docs/deploy.md)" ;;
esac

# 2. Azure session and cluster credentials.
az account show >/dev/null 2>&1 || die "not logged in to Azure: run 'az login'"
log "Credentials of ${AKS_NAME}"
az aks get-credentials --resource-group "${AKS_RESOURCE_GROUP}" --name "${AKS_NAME}" \
  --overwrite-existing >&2

# 3. The registry must exist, and the kubelet identity must be allowed to pull from it.
#    Terraform does both on our cluster; an evaluator's cluster may have neither.
registry="${ACR_NAME}.azurecr.io"
if [ -z "${SKIP_ACR_ATTACH:-}" ]; then
  if ! az acr show -n "${ACR_NAME}" >/dev/null 2>&1; then
    [ "$(az acr check-name -n "${ACR_NAME}" --query nameAvailable -o tsv)" = "true" ] \
      || die "registry ${ACR_NAME} is not in this subscription and its name is taken: choose another ACR_NAME"
    log "Creating registry ${ACR_NAME} (Basic) in ${AKS_RESOURCE_GROUP}"
    az acr create -g "${AKS_RESOURCE_GROUP}" -n "${ACR_NAME}" --sku Basic >/dev/null
  fi
  kubelet_id="$(az aks show -g "${AKS_RESOURCE_GROUP}" -n "${AKS_NAME}" \
    --query identityProfile.kubeletidentity.objectId -o tsv)"
  acr_id="$(az acr show -n "${ACR_NAME}" --query id -o tsv)"
  pulls="$(az role assignment list --assignee "${kubelet_id}" --scope "${acr_id}" \
    --role AcrPull --query 'length(@)' -o tsv)"
  if [ "${pulls}" = "0" ]; then
    log "Granting AcrPull on ${ACR_NAME} to the cluster"
    az aks update -g "${AKS_RESOURCE_GROUP}" -n "${AKS_NAME}" --attach-acr "${ACR_NAME}" >&2
  fi
fi

# Git tree hash of poll-application/<service> as it is on disk, uncommitted and untracked
# (not ignored) files included. Computed in a throwaway index: the real one is untouched.
working_tree_of() {
  local index tree
  index="$(mktemp)"
  cp "$(git -C "${root}" rev-parse --path-format=absolute --git-path index)" "${index}"
  GIT_INDEX_FILE="${index}" git -C "${root}" add -A -- poll-application
  tree="$(GIT_INDEX_FILE="${index}" git -C "${root}" write-tree)"
  rm -f "${index}"
  git -C "${root}" rev-parse "${tree}:poll-application/$1"
}

# 4. Images: given tag, or the current commit built and pushed here. A service whose
#    directory differs from HEAD gets its own tag, derived from its content: the change is
#    deployed even if not committed, and only that service rolls out.
image_tags=()
if [ -z "${IMAGE_TAG:-}" ]; then
  IMAGE_TAG="$(git -C "${root}" rev-parse HEAD)"
  az acr login --name "${ACR_NAME}" >&2
  for service in poll worker result; do
    tag="${IMAGE_TAG}"
    tree="$(working_tree_of "${service}")"
    if [ "${tree}" != "$(git -C "${root}" rev-parse "HEAD:poll-application/${service}")" ]; then
      tag="${IMAGE_TAG:0:12}-dirty-${tree:0:12}"
      image_tags+=(--set-string "${service}.image.tag=${tag}")
      log "${service} has uncommitted changes: tagged ${tag}"
    fi
    if az acr manifest show-metadata -r "${ACR_NAME}" -n "${service}:${tag}" >/dev/null 2>&1; then
      log "${service}:${tag} already in the registry"
    else
      log "Building ${service}:${tag}"
      docker buildx build --platform linux/amd64 --push \
        --tag "${registry}/${service}:${tag}" \
        "${root}/poll-application/${service}" >&2
    fi
  done
fi

# 5. Gateway prerequisites (cluster-wide, outside the chart: ADR-0003). Only installed when
#    absent, so a deploy by a namespaced identity needs no cluster-wide right.
if kubectl get gatewayclass traefik >/dev/null 2>&1; then
  ip="$(kubectl -n traefik get svc traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
fi
if [ -n "${ip:-}" ]; then
  domain="${ip}.nip.io"
else
  log "Installing Gateway API and Traefik"
  domain="$(BERNSTEIN_NAMESPACE="${namespace}" "${root}/scripts/install-gateway.sh")"
fi

# 6. The release. Rollback flag: --rollback-on-failure (Helm 4) or --atomic (Helm 3).
if helm upgrade --help | grep -q -- '--rollback-on-failure'; then
  rollback=(--rollback-on-failure --wait)
else
  rollback=(--atomic --wait)
fi

log "Deploying ${release} (tag ${IMAGE_TAG:0:12}, domain ${domain}, backups ${backup[1]#*=})"
# The password goes through a process substitution, not the command line: arguments are
# visible to every user of the machine in `ps`. jq escapes it into valid JSON (YAML).
helm upgrade --install "${release}" "${root}/charts/bernstein" \
  --namespace "${namespace}" --create-namespace \
  "${rollback[@]}" --timeout 10m \
  --set "global.registry=${registry}" \
  --set-string "global.tag=${IMAGE_TAG}" \
  "${image_tags[@]}" \
  --set-string "gateway.domain=${domain}" \
  "${backup[@]}" \
  --values <(jq -n --arg p "${POSTGRES_PASSWORD}" '{postgres: {password: $p}}') >&2

# 7. Result.
poll_url="http://poll.${domain}"
result_url="http://result.${domain}"
echo "poll:   ${poll_url}"
echo "result: ${result_url}"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "## Deployed ${IMAGE_TAG:0:12}"
    echo "- poll: ${poll_url}"
    echo "- result: ${result_url}"
  } >> "${GITHUB_STEP_SUMMARY}"
fi
