# Proving zero downtime: `zero-downtime-check.sh`

The defense judges zero downtime by requesting the application continuously while it is updated. [ADR-0005](adr/0005-zero-downtime-rolling-updates.md) makes the rollout safe on paper; this script produces the evidence, and shows what a failure looks like, so a green result means something.

Two scripts, one purpose each:

| Script | Purpose |
|---|---|
| `scripts/zero-downtime-check.sh` | Requests poll and result in a loop, prints every failure, exits 1 if there was one. Needs only `curl`. |
| `scripts/zero-downtime-demo.sh` (`make zdt-demo`) | The defense scenario: starts the checker, ships a visible change of poll, stops the checker. |

## Use

```sh
scripts/zero-downtime-check.sh http://poll.1.2.3.4.nip.io http://result.1.2.3.4.nip.io 120
```

The third argument is the duration in seconds (default 60; `0` runs until Ctrl-C or `kill`, and still prints the report). `INTERVAL=0.05` changes the pause between two requests of a probe (default 0.1 s). Run `helm upgrade`, `kubectl rollout restart` or `kubectl drain` in another terminal while it runs. The exit code is 0 for no error, 1 for at least one error or no request at all, 2 for bad usage, so it can run in CI after a deploy.

```
>> Requesting http://127.0.0.1:8765 and http://127.0.0.1:8765
>>   3s     104 requests  0 errors

probe              requests  errors       p95
poll-get                 26       0      2 ms
poll-post                26       0      2 ms
result-get               26       0      2 ms
result-socketio          26       0      3 ms
total                   104       0
OK: no error in 104 requests
```

(Run against a local stand-in server. On the cluster the p95 is tens of milliseconds.) With the server down, each failed request is printed as it happens and the exit code is 1:

```
22:28:46.758 FAIL poll-get: status 000 after 0.000087s (http://127.0.0.1:8765/)
FAILED: 36 error(s) in 36 request(s)
```

Status `000` is curl's way to say "no HTTP answer": connection refused, reset or timeout.

## What is requested, and why these four

| Probe | Request | What it catches |
|---|---|---|
| `poll-get` | `GET poll /` | Traefik sending traffic to a poll pod that is starting or stopping |
| `poll-post` | `POST poll /` with `vote=a` | The write path: poll to Redis. A pod can answer `GET` while its Redis connection is not ready. It casts **real votes**, visible in the result page. |
| `result-get` | `GET result /` | The result pod being replaced |
| `result-socketio` | `GET result /socket.io/?EIO=4&transport=polling` | The Socket.IO handshake the result page performs on load |

A request is a failure when the status is not 2xx or when it takes more than 2 seconds (`--max-time 2`): a hung connection is downtime for a user too.

The probes run as four background loops, not one loop of four requests: during an outage each request waits up to 2 s, and a single loop would then send far fewer requests, hiding how long the outage lasted.

## How the script is organised

The file is written as a list of small named functions followed by a short main part, to be read top to bottom:

| Function | Role |
|---|---|
| `send_request` | One `curl`, prints `<status> <seconds>`. The only place that knows curl's options. |
| `is_success` | Status starts with `2`. |
| `probe` | Loop: `send_request`, append the line to the probe's log file, print a `FAIL` line when `is_success` is false. |
| `start_probes`, `stop_probes` | Start the four probes in the background; ask them to stop through a `stop` file and `wait` for the last request. |
| `count_requests`, `count_errors`, `p95_milliseconds` | Read the log files. |
| `print_progress`, `print_report` | What the user sees. |

Each probe appends to its own file in a temporary directory (removed on exit) instead of sharing variables: background jobs cannot write to the parent's variables, and one file per probe avoids interleaved lines.

Details that are easy to get wrong:

- `curl ... || true` in `send_request`: curl exits non-zero on a timeout, and `set -e` would kill the script. The status `000` carries the failure.
- `grep --count` exits 1 when the count is 0, hence `|| true` in `count_errors`.
- `sleep 1 & wait $!` instead of `sleep 1`: bash only runs a signal trap after the current foreground command ends, but `wait` returns at once, so Ctrl-C ends the run within a moment.
- Background jobs in a script start with SIGINT ignored: Ctrl-C reaches only the main script, which then stops the probes cleanly. Use `kill -TERM` (not `-INT`) on the script when it was itself started in the background, as the demo does.
- The p95 is the value below which 95 % of the requests fall: durations sorted, rank `ceil(0.95 × n)`.

## The demo: `make zdt-demo`

```sh
export ACR_NAME=bernsteinacr
make zdt-demo
```

1. Copies `poll-application/poll/` to a temporary directory and appends `(demo-<timestamp>)` to the footer of `index.html`. The repository stays untouched, and the application code is not modified (CLAUDE.md).
2. Builds and pushes `poll:demo-<timestamp>` to the registry.
3. Starts the checker (duration `0`) on the URLs of the running release (read from `helm get values`), waits 5 s.
4. `helm upgrade --reuse-values --set-string poll.image.tag=demo-<timestamp> --wait`: only poll changes, through the per-component tag, `global.tag` stays.
5. Waits 5 s, stops the checker with `SIGTERM` and exits with its status.

Reload the poll page afterwards: the footer shows the new tag, and the report above says 0 errors.

## Acceptance checks (#27)

- Rollout of poll, worker, result: report 0 errors. Worker has no Service, so the checker only sees its effect indirectly: votes keep being counted. Check the vote total in the result page grows.
- The test can fail: these settings are not chart values, so temporarily edit `charts/bernstein/templates/poll/deployment.yaml` (`maxUnavailable: 1`, delete the `preStop` block), `helm upgrade` while the checker runs, and `FAIL` lines appear. Revert the edit afterwards. These runs need the real cluster and are batched at the end of the sprint.

## Rejected

- **k6, `hey`, `vegeta`**: stronger load tools (k6 stays an option for the autoscaler load test, #29), but a bash and curl script needs nothing installed on the defense laptop and can be read in two minutes.
- **A browser refresh**: nothing is recorded, and a failure of 200 ms is invisible.
