#!/usr/bin/env bash
# Bootstrap the Terraform remote state backend in the team Azure subscription.
#
# Creates (only if missing):
#   - resource group      bernstein-tfstate-rg
#   - storage account     versioning + soft delete, no shared keys, no public access
#   - blob container      tfstate (private)
# and grants "Storage Blob Data Contributor" on the storage account to you and
# to every teammate you list. Teammates also get "Contributor" on the
# subscription so they can create resources.
#
# Safe to run several times: every step checks before creating.
#
# Usage:
#   az login
#   ./bootstrap.sh
# The script asks for the subscription and the teammates' emails. If your
# directory forbids looking users up, enter their object ID instead; each
# teammate gets it with: az ad signed-in-user show --query id -o tsv

set -euo pipefail

LOCATION="francecentral"
RESOURCE_GROUP="bernstein-tfstate-rg"
CONTAINER="tfstate"
SOFT_DELETE_DAYS=30

log() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

assign_role() {
    local assignee="$1" role="$2" scope="$3"
    local existing
    existing=$(az role assignment list --assignee "$assignee" --role "$role" \
        --scope "$scope" --query 'length(@)' -o tsv)
    if [[ "$existing" -gt 0 ]]; then
        log "role '$role' already granted to $assignee"
    else
        log "granting '$role' to $assignee"
        az role assignment create --assignee-object-id "$assignee" \
            --assignee-principal-type User --role "$role" --scope "$scope" \
            --output none
    fi
}

az account show --output none 2>/dev/null || die "not logged in, run 'az login' first"

echo "Your subscriptions:"
az account list --query '[].{name:name, id:id}' -o table
CURRENT_SUB=$(az account show --query id -o tsv)
read -rp "Team subscription ID [$CURRENT_SUB]: " SUBSCRIPTION_ID
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-$CURRENT_SUB}"

read -rp "Teammates' emails or object IDs, separated by spaces (empty for none): " MEMBERS

az account set --subscription "$SUBSCRIPTION_ID"
SUBSCRIPTION_SCOPE="/subscriptions/$SUBSCRIPTION_ID"
TENANT_ID=$(az account show --query tenantId -o tsv)

# Resolve members to object IDs before creating anything, so a typo stops the
# script early instead of halfway through.
MEMBER_IDS=()
GUID_RE='^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$'
for member in $MEMBERS; do
    if [[ "$member" =~ $GUID_RE ]]; then
        id="$member"
    else
        # Direct lookup by UPN often works even when the directory forbids
        # listing users; fall back to a search on the mail field.
        id=$(az ad user show --id "$member" --query id -o tsv 2>/dev/null) ||
        id=$(az ad user list --filter "mail eq '$member'" --query '[0].id' -o tsv 2>/dev/null) ||
        id=""
    fi
    [[ -n "$id" ]] || die "cannot find $member in this directory. Ask them to run
  az ad signed-in-user show --query id -o tsv
and enter the ID it prints instead of their email."
    MEMBER_IDS+=("$id")
done

# Storage account names are global, 3-24 lowercase alphanumerics: derive a
# stable one from the subscription ID so every run picks the same name.
STORAGE_ACCOUNT="bernsteintf$(tr -d '-' <<<"$SUBSCRIPTION_ID" | cut -c1-12)"

# New subscriptions have most resource providers unregistered, and Azure then
# answers storage calls with a misleading "SubscriptionNotFound".
if [[ "$(az provider show --namespace Microsoft.Storage \
    --query registrationState -o tsv)" == "Registered" ]]; then
    log "provider Microsoft.Storage registered"
else
    log "registering provider Microsoft.Storage (can take a minute)"
    az provider register --namespace Microsoft.Storage --wait
fi

if [[ "$(az group exists --name "$RESOURCE_GROUP")" == "true" ]]; then
    log "resource group $RESOURCE_GROUP exists"
else
    log "creating resource group $RESOURCE_GROUP"
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
fi

if az storage account show --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null; then
    log "storage account $STORAGE_ACCOUNT exists"
else
    log "creating storage account $STORAGE_ACCOUNT"
    az storage account create \
        --name "$STORAGE_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --sku Standard_LRS \
        --kind StorageV2 \
        --min-tls-version TLS1_2 \
        --allow-blob-public-access false \
        --allow-shared-key-access false \
        --output none
fi

# Updating these properties to the same values is a no-op, so no check needed.
log "enabling versioning and soft delete"
az storage account blob-service-properties update \
    --account-name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --enable-versioning true \
    --enable-delete-retention true --delete-retention-days "$SOFT_DELETE_DAYS" \
    --enable-container-delete-retention true \
    --container-delete-retention-days "$SOFT_DELETE_DAYS" \
    --output none

# container-rm goes through the management plane, so it works right away
# without waiting for the data role assignment to propagate.
if [[ "$(az storage container-rm exists --storage-account "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" --name "$CONTAINER" -o tsv)" == "true" ]]; then
    log "container $CONTAINER exists"
else
    log "creating container $CONTAINER"
    az storage container-rm create --storage-account "$STORAGE_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" --name "$CONTAINER" \
        --public-access off --output none
fi

STORAGE_SCOPE=$(az storage account show --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" --query id -o tsv)

CALLER_ID=$(az ad signed-in-user show --query id -o tsv)
assign_role "$CALLER_ID" "Storage Blob Data Contributor" "$STORAGE_SCOPE"

for member in "${MEMBER_IDS[@]}"; do
    assign_role "$member" "Contributor" "$SUBSCRIPTION_SCOPE"
    assign_role "$member" "Storage Blob Data Contributor" "$STORAGE_SCOPE"
done

cat <<EOF

Backend ready. Role assignments can take a few minutes to apply.
Send this to your teammates:

  az login --tenant $TENANT_ID
  az account set --subscription $SUBSCRIPTION_ID
  cd infra/terraform
  terraform init -backend-config="storage_account_name=$STORAGE_ACCOUNT"
EOF
