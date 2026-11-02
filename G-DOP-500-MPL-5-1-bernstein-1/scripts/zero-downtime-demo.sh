#!/usr/bin/env bash
# Defense demo: change a visible string of poll, ship it with a rolling update and show,
# with scripts/zero-downtime-check.sh, that not one request failed meanwhile.
#
# Required environment:
#   ACR_NAME   registry the release already pulls from (without .azurecr.io)
# Optional:
#   NAMESPACE  namespace of the release (default: bernstein)
#
# The change is made in a temporary copy of poll/: the working tree stays untouched.
# Run it on a cluster already deployed with `make deploy`. Explained in
# docs/zero-downtime-check.md.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
namespace="${NAMESPACE:-bernstein}"
release="bernstein"
demo_tag="demo-$(date +%s)"

log() { echo ">> $*" >&2; }
die() { echo "error: $*" >&2; exit 1; }

# --- steps -------------------------------------------------------------------------------

check_inputs() {
  [ -n "${ACR_NAME:-}" ] || die "ACR_NAME is not set (see docs/deploy.md)"
  for tool in az docker helm; do
    command -v "${tool}" >/dev/null || die "${tool} is not installed (see CLAUDE.md: nix develop)"
  done
}

# Domain of the running release, e.g. 1.2.3.4.nip.io.
current_domain() {
  helm get values "${release}" --namespace "${namespace}" --output json | jq -r '.gateway.domain'
}

# Copy poll/ to a temporary directory and add the demo tag to the page footer.
prepare_changed_poll() {
  local copy="$1"
  cp -r "${root}/poll-application/poll/." "${copy}"
  sed -i "s|Processed by container ID {{hostname}}|Processed by container ID {{hostname}} (${demo_tag})|" \
    "${copy}/templates/index.html"
  grep -q "${demo_tag}" "${copy}/templates/index.html" || die "the page footer was not found in index.html"
}

build_and_push_poll() {
  local context="$1"
  az acr login --name "${ACR_NAME}" >&2
  docker buildx build --platform linux/amd64 --push \
    --tag "${ACR_NAME}.azurecr.io/poll:${demo_tag}" "${context}" >&2
}

# Only poll gets the new tag (poll.image.tag overrides global.tag); the rest is reused.
roll_out_poll() {
  helm upgrade "${release}" "${root}/charts/bernstein" --namespace "${namespace}" \
    --reuse-values --set-string "poll.image.tag=${demo_tag}" --wait --timeout 10m >&2
}

# --- main --------------------------------------------------------------------------------

check_inputs
domain="$(current_domain)"
[ -n "${domain}" ] && [ "${domain}" != "null" ] || die "release ${release} has no gateway.domain: deploy it first"

build_context="$(mktemp -d)"
checker_pid=""
cleanup() {
  [ -z "${checker_pid}" ] || kill "${checker_pid}" 2>/dev/null || true
  rm -rf "${build_context}"
}
trap cleanup EXIT

prepare_changed_poll "${build_context}"
build_and_push_poll "${build_context}"

log "Starting the checker on poll.${domain} and result.${domain}"
"${root}/scripts/zero-downtime-check.sh" "http://poll.${domain}" "http://result.${domain}" 0 &
checker_pid=$!
sleep 5   # a few seconds of requests before the rollout, to show the steady state

log "Rolling out poll:${demo_tag}"
roll_out_poll
sleep 5   # and a few after it

log "Rollout done: stopping the checker"
kill -TERM "${checker_pid}"
checker_status=0
wait "${checker_pid}" || checker_status=$?
checker_pid=""

echo "Open http://poll.${domain} : the footer ends with (${demo_tag})." >&2
exit "${checker_status}"
