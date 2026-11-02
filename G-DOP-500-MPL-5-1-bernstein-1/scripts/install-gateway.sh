#!/usr/bin/env bash
# Install the cluster-wide prerequisites of the Gateway: Gateway API CRDs (standard
# channel) and Traefik. Idempotent: safe to run again. Prints the value to pass to the
# bernstein chart as `--set-string gateway.domain=...` on its last line.
#
# Uses the current kubectl context. Explained in docs/gateway.md.
#
# BERNSTEIN_NAMESPACE  namespace of the bernstein release (default: bernstein). Traefik only
#                      lets HTTPRoutes of that namespace use the sticky-session TraefikService
#                      of result (#26).
set -euo pipefail

GATEWAY_API_VERSION="v1.6.3"
TRAEFIK_CHART_VERSION="41.7.1"
NAMESPACE="traefik"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ">> Gateway API CRDs ${GATEWAY_API_VERSION} (standard channel)" >&2
kubectl apply --server-side -f \
  "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml" >&2

echo ">> Traefik chart ${TRAEFIK_CHART_VERSION}" >&2
helm repo add traefik https://traefik.github.io/charts --force-update >&2
helm upgrade --install traefik traefik/traefik \
  --version "${TRAEFIK_CHART_VERSION}" \
  --namespace "${NAMESPACE}" --create-namespace \
  --values "${root}/infra/gateway/traefik-values.yaml" \
  --set "providers.kubernetesGateway.crossProviderNamespaces={${BERNSTEIN_NAMESPACE:-bernstein}}" \
  --wait >&2

echo ">> Waiting for the public IP" >&2
ip=""
for _ in $(seq 1 60); do
  ip="$(kubectl -n "${NAMESPACE}" get svc traefik \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"
  [ -n "${ip}" ] && break
  sleep 5
done
[ -n "${ip}" ] || { echo "no public IP after 5 minutes" >&2; exit 1; }

echo "${ip}.nip.io"
