# 1. Static checks (no cluster, no cost)

What CI runs on every pull request, plus negative tests proving the checks can fail. Run from the repository root with `$OK` set ([README](README.md#session-variables)).

## static-1: the chart lints

**Why:** a chart that does not lint cannot be deployed.

```sh
helm lint --strict charts/bernstein $OK
```

**Expect:** `1 chart(s) linted, 0 chart(s) failed`. `--strict` turns warnings into failures.

**If it fails:** the message names the template and line.

## static-2: the chart renders and the output is valid Kubernetes

**Why:** `helm template` proves the Go templates evaluate; `kubeconform` proves the YAML matches the Kubernetes API schema of the version AKS runs.

```sh
helm template bernstein charts/bernstein $OK | wc -l
helm template bernstein charts/bernstein $OK \
  | nix shell nixpkgs#kubeconform -c kubeconform -strict -summary -kubernetes-version 1.36.0
```

**Expect:** the first prints several hundred lines. The second ends with (count as of 2026-10-14):

```
Summary: 22 resources found parsing stdin - Valid: 22, Invalid: 0, Errors: 0, Skipped: 0
```

Also render the gateway objects, which need a domain:

```sh
helm template bernstein charts/bernstein $OK --set-string gateway.domain=1.2.3.4.nip.io \
  | grep -E '^kind: (Gateway|HTTPRoute|TraefikService)$'
```

**Expect:** four lines: `Gateway`, `HTTPRoute` twice (poll and result), `TraefikService` (the sticky cookie of result).

## static-3: required values are enforced

**Why:** a deploy without registry, tag or password must stop at render time with a readable message, not produce a broken release.

```sh
helm template bernstein charts/bernstein --set-string global.tag=dev --set-string postgres.password=x
helm template bernstein charts/bernstein --set global.registry=r.io --set-string postgres.password=x
helm template bernstein charts/bernstein --set global.registry=r.io --set-string global.tag=dev
helm template bernstein charts/bernstein $OK --set poll.autoscaling.minReplicas=9
```

**Expect:** each command fails (exit code 1), with, in order:

```
- at '/global/registry': '' does not match pattern '^[A-Za-z0-9.-]+(:[0-9]+)?(/[a-z0-9._-]+)*$'
- at '/global/tag': '' does not match pattern '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$'
Error: execution error at (bernstein/templates/postgres/secret.yaml:10:15): postgres.password is required: pass --set-string postgres.password="$POSTGRES_PASSWORD", or set postgres.existingSecret
Error: execution error at (bernstein/templates/poll/hpa.yaml:1:4): values: poll.autoscaling.maxReplicas (5) is below minReplicas (9)
```

The first two come from `values.schema.json`, the last two from `fail` calls in the templates.

**If a command succeeds:** the guard is missing: fail the test and open an issue.

## static-4: the all-digit tag trap

**Why:** an all-digit short SHA passed with `--set` becomes a number and breaks the schema. `deploy.sh` uses `--set-string`.

```sh
helm template bernstein charts/bernstein --set global.registry=r.io --set global.tag=1234567 --set-string postgres.password=x
helm template bernstein charts/bernstein --set global.registry=r.io --set-string global.tag=1234567 --set-string postgres.password=x | grep 'image:' | head -3
```

**Expect:** the first fails with `- at '/global/tag': got number, want string`; the second prints images ending in `:1234567`.

## static-5: every container has requests and limits

**Why:** CI enforces it ([resources.md](../resources.md)); the quota would refuse pods without them.

```sh
helm template bernstein charts/bernstein $OK \
  | nix shell nixpkgs#yq-go -c yq 'select(.kind=="Deployment" or .kind=="StatefulSet") | .metadata.name + " " + (.spec.template.spec.containers[] | .name + " " + (.resources|tojson))'
```

**Expect:** one line per container (poll, worker, result, postgres, redis), each with `requests` and `limits` (CPU and memory; the CPU limit policy is [ADR-0006](../adr/0006-cpu-limits.md)). If one prints `{}` or lacks a limit, fail.

## static-6: Terraform

```sh
cd infra/terraform
terraform fmt -check -recursive
terraform init -backend=false >/dev/null
terraform validate
cd ../..
```

**Expect:** `fmt` prints nothing and exits 0; `validate` prints `Success! The configuration is valid.`

## static-7: no secret in the repository

**Why:** the subject forbids `POSTGRES_PASSWORD` in the repository.

```sh
git grep -n -i -E 'POSTGRES_PASSWORD\s*[:=]\s*["'\'']?[A-Za-z0-9]' -- . ':!docs' ':!poll-application' ':!*.md'
git grep -n -i -E '(password|secret|token)\s*[:=]\s*["'\''][^"'\'' ]{6,}' -- charts infra scripts .github
git log -p --all -S"$POSTGRES_PASSWORD" --oneline | head
```

**Expect:** the first two print nothing, or only empty values / `dev` placeholders / variable references (`${...}`, `$p`). The last prints nothing (use the real password you export in file 2; skip if not exported yet, re-run after).

**If a real secret appears:** stop. Rotate it first, then open an issue; history rewrite is a team decision.

## static-8: images build and run

**Why:** CI builds them without running; this checks they start.

```sh
for s in poll worker result; do docker build -q -t bernstein-$s:test poll-application/$s; done
docker run --rm -d --name t-poll -e REDIS_HOST=127.0.0.1 -p 18080:80 bernstein-poll:test
```

In the browser, open `http://localhost:18080`, then `http://localhost:18080/healthz` and `http://localhost:18080/readyz`. Click a button on the first page. Then `docker rm -f t-poll`.

**Expect:**
- the three builds print image IDs;
- the poll page shows the four buttons and the footer *Processed by container ID* followed by the container's short id;
- `/healthz` shows `ok`, `/readyz` shows `not ready` (no Redis: readiness depends on it, liveness must not);
- clicking a button gives an `Internal Server Error` page: there is no Redis to queue the vote. Expected here; on the cluster the same click gives ✔.

The images must run as non-root: `docker run --rm --entrypoint id bernstein-result:test` shows `uid=1000`.

## static-9: pull request checks are green

```sh
gh pr checks <number>      # on any open PR
```

**Expect:** all checks `pass` (lint, chart validation, requests/limits, Terraform, image builds, Trivy). Required checks are listed in [ci-pull-requests.md](../ci-pull-requests.md).
