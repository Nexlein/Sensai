#!/usr/bin/env bash
# Request poll and result continuously and report every failure: the evidence that a
# rollout (helm upgrade, node drain, pod kill) did not interrupt the application.
#
# Usage: zero-downtime-check.sh <poll-url> <result-url> [duration]
#   poll-url, result-url  e.g. http://poll.1.2.3.4.nip.io  http://result.1.2.3.4.nip.io
#   duration              seconds to run (default 60); 0 runs until SIGINT or SIGTERM
# Optional:
#   INTERVAL              seconds between two requests of one probe (default 0.1)
#
# Four probes run in parallel, so a slow answer on one does not delay the others:
#   poll-get         GET  poll   /
#   poll-post        POST poll   /          (a real vote: it is counted in the result page)
#   result-get       GET  result /
#   result-socketio  GET  result /socket.io/?EIO=4&transport=polling
# A request fails when its status is not 2xx or when it takes more than 2 seconds.
# Each failure is printed on stderr with its time; the totals are printed at the end.
#
# Exit code: 0 no error, 1 at least one error (or no request at all), 2 bad usage.
# Explained in docs/zero-downtime-check.md.
set -euo pipefail

REQUEST_TIMEOUT_SECONDS=2
PROBE_NAMES=(poll-get poll-post result-get result-socketio)

usage() {
  echo "usage: $0 <poll-url> <result-url> [duration-in-seconds]" >&2
  exit 2
}

fail_usage() {
  echo "error: $1" >&2
  usage
}

# ---------------------------------------------------------------------------------------
# One request
# ---------------------------------------------------------------------------------------

# Send one request and print "<http status> <seconds>". Extra arguments go to curl.
# On a timeout or a refused connection curl still prints the status 000, and its non-zero
# exit code is ignored here: the failure is reported through the status.
send_request() {
  local url="$1"
  shift
  curl --silent --output /dev/null --max-time "${REQUEST_TIMEOUT_SECONDS}" \
    --write-out '%{http_code} %{time_total}' "$@" "${url}" 2>/dev/null || true
}

is_success() {
  local status="$1"
  [[ "${status}" == 2* ]]
}

now() {
  date +%T.%3N
}

# ---------------------------------------------------------------------------------------
# Probes: each one requests in a loop and appends "<status> <seconds>" to its log file
# ---------------------------------------------------------------------------------------

log_file() {
  local probe_name="$1"
  echo "${work_dir}/${probe_name}.log"
}

stop_requested() {
  [ -e "${work_dir}/stop" ]
}

# probe <name> <url> [curl options]
probe() {
  local probe_name="$1" url="$2"
  shift 2
  local answer status seconds

  while ! stop_requested; do
    answer="$(send_request "${url}" "$@")"
    status="${answer%% *}"
    seconds="${answer##* }"
    echo "${status} ${seconds}" >> "$(log_file "${probe_name}")"

    if ! is_success "${status}"; then
      echo "$(now) FAIL ${probe_name}: status ${status} after ${seconds}s (${url})" >&2
    fi
    sleep "${INTERVAL:-0.1}"
  done
}

start_probes() {
  for probe_name in "${PROBE_NAMES[@]}"; do
    : > "$(log_file "${probe_name}")"
  done

  probe poll-get "${poll_url}/" &
  probe poll-post "${poll_url}/" --data 'vote=a' &
  probe result-get "${result_url}/" &
  probe result-socketio "${result_url}/socket.io/?EIO=4&transport=polling" &
}

# Let every probe finish its current request (at most the timeout), then return.
stop_probes() {
  touch "${work_dir}/stop"
  wait
}

# ---------------------------------------------------------------------------------------
# Counting what the probes logged
# ---------------------------------------------------------------------------------------

# Number of requests in the given log files.
count_requests() {
  cat "$@" | wc -l
}

# Number of failed requests in the given log files: lines whose status does not start
# with 2 (grep -v inverts the match, -c counts; it exits 1 on a count of 0, hence || true).
count_errors() {
  cat "$@" | grep --invert-match --count '^2' || true
}

# 95th percentile of the durations of one log file, in milliseconds: 95 % of the requests
# were at least that fast.
p95_milliseconds() {
  local log="$1"
  cut --delimiter=' ' --fields=2 "${log}" | sort --numeric-sort | awk '
    { durations[NR] = $1 }
    END {
      rank = int(NR * 0.95)
      if (rank < NR * 0.95) rank++
      printf "%.0f ms", durations[rank] * 1000
    }'
}

# ---------------------------------------------------------------------------------------
# What the user sees
# ---------------------------------------------------------------------------------------

print_progress() {
  local elapsed="$1"
  local logs=("${work_dir}"/*.log)
  printf '\r>> %3ds  %6d requests  %d errors ' \
    "${elapsed}" "$(count_requests "${logs[@]}")" "$(count_errors "${logs[@]}")" >&2
}

print_report() {
  printf '\n%-17s %9s %7s %9s\n' probe requests errors p95
  for probe_name in "${PROBE_NAMES[@]}"; do
    local log
    log="$(log_file "${probe_name}")"
    local p95="-"
    if [ "$(count_requests "${log}")" -gt 0 ]; then
      p95="$(p95_milliseconds "${log}")"
    fi
    printf '%-17s %9d %7d %9s\n' \
      "${probe_name}" "$(count_requests "${log}")" "$(count_errors "${log}")" "${p95}"
  done
  printf '%-17s %9d %7d\n' total "${total_requests}" "${total_errors}"
}

# ---------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------

[ $# -ge 2 ] && [ $# -le 3 ] || usage
poll_url="${1%/}"
result_url="${2%/}"
duration="${3:-60}"
[[ "${duration}" =~ ^[0-9]+$ ]] || fail_usage "duration must be a number of seconds"
command -v curl >/dev/null || fail_usage "curl is not installed"

work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT

# Ctrl-C or `kill` ends the run early but still prints the report. The probes are
# background jobs, which bash starts with SIGINT ignored: only this script is interrupted.
interrupted=""
trap 'interrupted=1' INT TERM

duration_not_over() {
  [ "${duration}" -eq 0 ] || [ "${SECONDS}" -lt $((start + duration)) ]
}

echo ">> Requesting ${poll_url} and ${result_url}" >&2
start="${SECONDS}"
start_probes

while [ -z "${interrupted}" ] && duration_not_over; do
  # `sleep & wait` instead of `sleep`: a signal interrupts `wait` at once.
  sleep 1 &
  wait $! || true
  print_progress $((SECONDS - start))
done
echo >&2

stop_probes

logs=("${work_dir}"/*.log)
total_requests="$(count_requests "${logs[@]}")"
total_errors="$(count_errors "${logs[@]}")"
print_report

if [ "${total_requests}" -eq 0 ] || [ "${total_errors}" -gt 0 ]; then
  echo "FAILED: ${total_errors} error(s) in ${total_requests} request(s)" >&2
  exit 1
fi
echo "OK: no error in ${total_requests} requests" >&2
