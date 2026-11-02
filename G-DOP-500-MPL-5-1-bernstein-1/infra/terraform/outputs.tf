output "resource_group" {
  description = "Name of the resource group."
  value       = azurerm_resource_group.main.name
}

output "acr_login_server" {
  description = "Registry hostname used to tag and push images."
  value       = azurerm_container_registry.main.login_server
}

output "aks_name" {
  description = "Name of the AKS cluster, for az aks get-credentials."
  value       = azurerm_kubernetes_cluster.main.name
}

output "budget_id" {
  description = "ID of the monthly budget on the subscription."
  value       = azurerm_consumption_budget_subscription.main.id
}

output "github_push_client_id" {
  description = "Client ID of the identity GitHub Actions uses to push images (repository variable AZURE_CLIENT_ID)."
  value       = azurerm_user_assigned_identity.github_push.client_id
}

output "github_deploy_client_id" {
  description = "Client ID of the identity GitHub Actions uses to deploy to the cluster (repository variable AZURE_DEPLOY_CLIENT_ID)."
  value       = azurerm_user_assigned_identity.github_deploy.client_id
}

output "backup_storage_account" {
  description = "Storage account holding the PostgreSQL backups (chart value postgres.backup.storageAccount)."
  value       = azurerm_storage_account.backup.name
}

output "backup_container" {
  description = "Blob container holding the PostgreSQL backups (chart value postgres.backup.container)."
  value       = azurerm_storage_container.backup.name
}

output "backup_client_id" {
  description = "Client ID of the identity the backup CronJob uses (chart value postgres.backup.clientId)."
  value       = azurerm_user_assigned_identity.postgres_backup.client_id
}

output "tenant_id" {
  description = "Entra tenant ID (repository variable AZURE_TENANT_ID)."
  value       = data.azurerm_subscription.current.tenant_id
}

output "subscription_id" {
  description = "Subscription ID (repository variable AZURE_SUBSCRIPTION_ID)."
  value       = data.azurerm_subscription.current.subscription_id
}
