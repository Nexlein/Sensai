provider "azurerm" {
  features {}

  use_cli = true

  resource_providers_to_register = [
    "Microsoft.Compute",
    "Microsoft.ContainerRegistry",
    "Microsoft.Consumption",
    "Microsoft.ContainerService",
    "Microsoft.ManagedIdentity",
    "Microsoft.Network",
    "Microsoft.Storage",
  ]
}
