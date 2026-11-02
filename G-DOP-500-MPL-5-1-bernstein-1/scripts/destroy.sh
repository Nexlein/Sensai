#!/usr/bin/env bash
# Remove the Bernstein release from the current kubectl context. The data disks of
# PostgreSQL and Redis survive `helm uninstall` (StatefulSet PVCs are never garbage
# collected) and keep billing: pass DELETE_PVC=1 to delete them too, which loses the data.
# Traefik and the Gateway API CRDs are cluster-wide and stay. Explained in docs/deploy.md.
set -euo pipefail

namespace="${NAMESPACE:-bernstein}"
release="bernstein"

helm uninstall "${release}" --namespace "${namespace}" --wait --ignore-not-found

if [ "${DELETE_PVC:-}" = "1" ]; then
  echo ">> Deleting the data volumes of ${release}" >&2
  kubectl -n "${namespace}" delete pvc -l "app.kubernetes.io/instance=${release}" --ignore-not-found
else
  echo ">> Data volumes kept (still billed). DELETE_PVC=1 removes them:" >&2
  kubectl -n "${namespace}" get pvc -l "app.kubernetes.io/instance=${release}" >&2 || true
fi
