# Deploy variables (docs/deploy.md), optional and gitignored.
-include .env

RESOURCE_GROUP ?= bernstein-rg
AKS_NAME       ?= bernstein-aks

AKS_ARGS = --resource-group $(RESOURCE_GROUP) --name $(AKS_NAME)

.PHONY: help cluster-stop cluster-start cluster-status deploy destroy zdt-demo

help:
	@echo "deploy          deploy Bernstein on the cluster (env vars: docs/deploy.md)"
	@echo "destroy         uninstall Bernstein; DELETE_PVC=1 also deletes the data volumes"
	@echo "zdt-demo        change poll, roll it out and prove zero errors (env: ACR_NAME)"
	@echo "cluster-stop    deallocate the AKS nodes (config and PV disks are kept)"
	@echo "cluster-start   start the AKS cluster and wait for the nodes to be Ready"
	@echo "cluster-status  show the cluster power state"

deploy:
	./scripts/deploy.sh

destroy:
	./scripts/destroy.sh

zdt-demo:
	./scripts/zero-downtime-demo.sh

cluster-stop:
	az aks stop $(AKS_ARGS)
	@$(MAKE) --no-print-directory cluster-status

cluster-start:
	az aks start $(AKS_ARGS)
	az aks get-credentials $(AKS_ARGS) --overwrite-existing
	kubectl wait --for=condition=Ready nodes --all --timeout=10m
	kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded
	@$(MAKE) --no-print-directory cluster-status

cluster-status:
	@az aks show $(AKS_ARGS) --query '{name:name, power:powerState.code, provisioning:provisioningState}' --output table
