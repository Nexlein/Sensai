# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Root `README.md`: prerequisites, the credentials to set and where they go, deploy, zero-downtime update, rollback, teardown and troubleshooting (#36).
- `make` reads the deploy variables from a gitignored `.env` file at the repository root, if present.
- `make deploy` checks for `docker buildx` before touching Azure, instead of failing at the first build.
- `make deploy` creates the registry `ACR_NAME` (Basic, in the cluster's resource group) when it does not exist, so a fresh cluster needs nothing else.
- `make deploy` enables the PostgreSQL backup CronJob when `BACKUP_STORAGE_ACCOUNT`, `BACKUP_CONTAINER` and `BACKUP_CLIENT_ID` are set (all three or none), and the CI deploy job sets them from repository variables (#73).
- Manual acceptance test suite in `docs/testing/`: static checks, deploy, functional, resilience and zero downtime, data and restore, operations, with a result sheet.
- result runs 2 replicas with a sticky-session cookie set by Traefik (`TraefikService` `result-sticky`), so Socket.IO no longer fails with `Session ID unknown`; `install-gateway.sh` allows the release namespace in `crossProviderNamespaces` (#26).
- Scheduled PostgreSQL backup: CronJob `postgres-backup` (`pg_dump -Fc` to Azure Blob every 6 h through workload identity, off by default), Terraform storage account with 7-day retention and identity, and `docs/runbooks/restore.md` (#31).
- PodDisruptionBudgets (`minAvailable: 1`) for poll, result and worker when they run more than one pod, and topology spread constraints over nodes and zones, so a node drain keeps the application up (#28). New document `docs/helm-availability.md`.
- HorizontalPodAutoscaler for poll (2 to 5 pods at 70 % CPU, 120 s scale-down window), also available for result once sticky sessions exist; the Deployment no longer sets `replicas` while it is enabled, so `helm upgrade` keeps the scaled count (#29). New document `docs/helm-autoscaling.md`.
- CPU and memory requests and limits on every workload, a namespace `LimitRange` and `ResourceQuota` (`namespace.*` values), and a CI check that every rendered container sets all four (#30, ADR-0006). New document `docs/resources.md`.
- Zero-downtime verification: `scripts/zero-downtime-check.sh` (continuous requests on poll and result, error report, exit code) and `make zdt-demo` (#27). New document `docs/zero-downtime-check.md`.
- Zero-downtime rolling updates for poll, result and worker: `maxUnavailable: 0`, `minReadySeconds`, `preStop` sleep and a 40 s grace period, `revisionHistoryLimit: 5` (#25, ADR-0005).
- One-command deployment: `scripts/deploy.sh` (`make deploy`) and `scripts/destroy.sh` (`make destroy`), and a `deploy` job on `main` using a dedicated OIDC identity `bernstein-github-deploy` (#23, #24). New document `docs/terraform.md`.
- Public entry point: `scripts/install-gateway.sh` (Gateway API CRDs and Traefik), and a `Gateway` with host-based `HTTPRoute`s for poll and result, enabled by `gateway.domain` (#22).
- worker Deployment (2 replicas, probes on `/healthz` and `/readyz`, no Service), and the `bernstein.env.redis` / `bernstein.env.postgres` helpers shared by poll, worker and result (#20).
- result Deployment (1 replica, PostgreSQL settings from values) and the `result` Service (#21).
- poll Deployment (2 replicas, labels of the choices set from values) and the `poll` Service (#19).
- Redis 8 StatefulSet with password, append-only persistence and `noeviction` memory limit, and the `redis` Service (#18).
- Helm hook Job applying `schema.sql` before each upgrade (#16).

### Fixed

- `make deploy` deploys uncommitted changes: a service whose directory differs from HEAD is built under its own content-based tag (`<sha>-dirty-<tree>`) and only that service rolls out. Before, the HEAD image already existed, so the deploy changed nothing.
- CI logins to Azure (image push, deploy) no longer fail with `AADSTS700213`: the GitHub federated credentials use the repository's immutable OIDC subject `owner@id/name@id` (#77).
- First `helm install --wait` (so the first `make deploy`) no longer times out: the schema is applied by PostgreSQL's initdb directory (`postgres-initdb` ConfigMap) instead of a `post-install` hook, which Helm never ran because `result` could not become Ready without the table (#61).
