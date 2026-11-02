terraform {
  backend "azurerm" {
    resource_group_name = "bernstein-tfstate-rg"
    container_name      = "tfstate"
    key                 = "bernstein.tfstate"
    use_cli             = true
    use_azuread_auth    = true
  }
}
