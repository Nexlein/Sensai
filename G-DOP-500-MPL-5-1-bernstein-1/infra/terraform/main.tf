resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

resource "azurerm_container_registry" "main" {
  name                = var.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = var.tags
}

resource "azurerm_kubernetes_cluster" "main" {
  name                      = var.aks_name
  resource_group_name       = azurerm_resource_group.main.name
  location                  = azurerm_resource_group.main.location
  dns_prefix                = var.aks_name
  kubernetes_version        = var.kubernetes_version
  automatic_upgrade_channel = "patch"
  oidc_issuer_enabled       = true
  workload_identity_enabled = true
  tags                      = var.tags

  default_node_pool {
    name                        = "system"
    vm_size                     = var.node_vm_size
    auto_scaling_enabled        = true
    min_count                   = var.node_min_count
    max_count                   = var.node_max_count
    zones                       = var.availability_zones
    temporary_name_for_rotation = "systemtmp"

    upgrade_settings {
      max_surge = "10%"
    }
  }

  node_provisioning_profile {
    mode = "Manual"
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_data_plane  = "cilium"
    network_policy      = "cilium"
  }
}

resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                            = azurerm_container_registry.main.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}

data "azurerm_subscription" "current" {}

resource "azurerm_consumption_budget_subscription" "main" {
  name            = "bernstein-monthly"
  subscription_id = data.azurerm_subscription.current.id
  amount          = var.budget_amount
  time_grain      = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = var.budget_actual_thresholds
    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThanOrEqualTo"
      threshold_type = "Actual"
      contact_emails = var.budget_contact_emails
    }
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThanOrEqualTo"
    threshold_type = "Forecasted"
    contact_emails = var.budget_contact_emails
  }
}

resource "azurerm_user_assigned_identity" "github_push" {
  name                = "bernstein-github-push"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

resource "azurerm_federated_identity_credential" "github_push" {
  for_each = toset(var.github_push_branches)

  name                      = "github-${each.value}"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_push.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:${var.github_repository}:ref:refs/heads/${each.value}"
}

resource "azurerm_user_assigned_identity" "github_deploy" {
  name                = "bernstein-github-deploy"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

# Only a job running in the GitHub environment gets a token with this subject, so the
# environment's protection rules (approval, branch restriction) gate access to the cluster.
resource "azurerm_federated_identity_credential" "github_deploy" {
  name                      = "github-environment-${var.github_deploy_environment}"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_deploy.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:${var.github_repository}:environment:${var.github_deploy_environment}"
}

resource "azurerm_role_assignment" "github_aks_user" {
  scope                            = azurerm_kubernetes_cluster.main.id
  role_definition_name             = "Azure Kubernetes Service Cluster User Role"
  principal_id                     = azurerm_user_assigned_identity.github_deploy.principal_id
  skip_service_principal_aad_check = true
}

locals {
  backup_storage_account_name = var.backup_storage_account_name != "" ? var.backup_storage_account_name : "bernsteinbk${substr(replace(data.azurerm_subscription.current.subscription_id, "-", ""), 0, 12)}"
}

# Shared keys are disabled: the only way in is an Entra token, so no storage key can leak.
resource "azurerm_storage_account" "backup" {
  name                            = local.backup_storage_account_name
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  tags                            = var.tags
}

resource "azurerm_storage_container" "backup" {
  name                  = "postgres-backups"
  storage_account_id    = azurerm_storage_account.backup.id
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "backup" {
  storage_account_id = azurerm_storage_account.backup.id

  rule {
    name    = "delete-old-backups"
    enabled = true

    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["${azurerm_storage_container.backup.name}/"]
    }

    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = var.backup_retention_days
      }
    }
  }
}

resource "azurerm_user_assigned_identity" "postgres_backup" {
  name                = "bernstein-postgres-backup"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

# Only pods running as this ServiceAccount, in this namespace, on this cluster get a token for the identity.
resource "azurerm_federated_identity_credential" "postgres_backup" {
  name                      = "aks-${var.backup_namespace}-${var.backup_service_account}"
  user_assigned_identity_id = azurerm_user_assigned_identity.postgres_backup.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject                   = "system:serviceaccount:${var.backup_namespace}:${var.backup_service_account}"
}

# Scoped to the one container, not the account.
resource "azurerm_role_assignment" "postgres_backup_blob" {
  scope                            = azurerm_storage_container.backup.id
  role_definition_name             = "Storage Blob Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.postgres_backup.principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "github_acr_push" {
  scope                            = azurerm_container_registry.main.id
  role_definition_name             = "AcrPush"
  principal_id                     = azurerm_user_assigned_identity.github_push.principal_id
  skip_service_principal_aad_check = true
}
