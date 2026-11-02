variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "austriaeast"
}

variable "resource_group_name" {
  description = "Name of the resource group holding the cluster and registry."
  type        = string
  default     = "bernstein-rg"
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project    = "bernstein"
    managed_by = "terraform"
  }
}

variable "acr_name" {
  description = "Globally unique name of the container registry (5-50 alphanumeric chars)."
  type        = string
  default     = "bernsteinacr"

  validation {
    condition     = can(regex("^[a-zA-Z0-9]{5,50}$", var.acr_name))
    error_message = "acr_name must be 5-50 alphanumeric characters."
  }
}

variable "aks_name" {
  description = "Name of the AKS cluster."
  type        = string
  default     = "bernstein-aks"
}

variable "kubernetes_version" {
  description = "Kubernetes minor version; patches are applied automatically."
  type        = string
  default     = "1.36"
}

variable "node_vm_size" {
  description = "VM size of the system node pool."
  type        = string
  default     = "Standard_DS2_v2_Promo"
}

variable "node_min_count" {
  description = "Minimum number of nodes in the system pool."
  type        = number
  default     = 2
}

variable "node_max_count" {
  description = "Maximum number of nodes in the system pool."
  type        = number
  default     = 2
}

variable "availability_zones" {
  description = "Availability zones to spread nodes across; empty list if the region has none."
  type        = list(string)
  default     = ["1", "2", "3"]
}

variable "budget_amount" {
  description = "Monthly budget of the subscription, in its billing currency."
  type        = number
  default     = 60
}

variable "budget_start_date" {
  description = "First day of the first budgeted month (RFC3339); must be the first of a month, not in a past month at creation."
  type        = string
  default     = "2026-10-01T00:00:00Z"

  validation {
    condition     = can(regex("^\\d{4}-\\d{2}-01T00:00:00Z$", var.budget_start_date))
    error_message = "budget_start_date must be the first day of a month, e.g. 2026-10-01T00:00:00Z."
  }
}

variable "budget_actual_thresholds" {
  description = "Percentages of the budget actually spent that trigger an e-mail alert."
  type        = list(number)
  default     = [50, 80, 100]
}

variable "budget_contact_emails" {
  description = "Addresses receiving the budget alerts; no default so that alerts always reach a real inbox."
  type        = list(string)

  validation {
    condition     = length(var.budget_contact_emails) > 0
    error_message = "At least one budget contact e-mail is required."
  }
}

variable "github_repository" {
  description = "GitHub repository in the OIDC subject format: owner@owner_id/name@repo_id (immutable subject, see actions/oidc/customization/sub)."
  type        = string
  default     = "EpitechPGE3-2026@216019158/G-DOP-500-MPL-5-1-bernstein-1@1405326350"
}

variable "github_deploy_environment" {
  description = "GitHub environment whose jobs may deploy to the cluster through OIDC."
  type        = string
  default     = "production"
}

variable "backup_storage_account_name" {
  description = "Globally unique name of the storage account holding the PostgreSQL backups (3-24 lowercase alphanumeric chars). Empty: bernsteinbk<first 12 hex chars of the subscription id>, like the state account."
  type        = string
  default     = ""

  validation {
    condition     = var.backup_storage_account_name == "" || can(regex("^[a-z0-9]{3,24}$", var.backup_storage_account_name))
    error_message = "backup_storage_account_name must be empty or 3-24 lowercase alphanumeric characters."
  }
}

variable "backup_retention_days" {
  description = "Days after which a backup blob is deleted by the lifecycle rule."
  type        = number
  default     = 7
}

variable "backup_namespace" {
  description = "Kubernetes namespace of the release; part of the subject of the workload identity credential."
  type        = string
  default     = "bernstein"
}

variable "backup_service_account" {
  description = "Name of the Kubernetes ServiceAccount used by the backup CronJob; part of the subject of the workload identity credential."
  type        = string
  default     = "postgres-backup"
}

variable "github_push_branches" {
  description = "Branches whose workflows may push images; one federated credential each."
  type        = list(string)
  default     = ["dev", "main"]
}
