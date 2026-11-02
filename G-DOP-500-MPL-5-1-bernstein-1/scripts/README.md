# scripts

| Script | Purpose | Explained in |
|---|---|---|
| `deploy.sh` | One-command deployment (`make deploy`) | [docs/deploy.md](../docs/deploy.md) |
| `destroy.sh` | Uninstall the release, optionally the data volumes (`make destroy`) | [docs/deploy.md](../docs/deploy.md) |
| `zero-downtime-check.sh` | `<poll-url> <result-url> [seconds]`: request poll and result continuously, exit 1 on any error. Run it during a rollout | [docs/zero-downtime-check.md](../docs/zero-downtime-check.md) |
| `zero-downtime-demo.sh` | Change poll, roll it out, prove zero errors (`make zdt-demo`, needs `ACR_NAME`) | [docs/zero-downtime-check.md](../docs/zero-downtime-check.md) |
| `install-gateway.sh` | Gateway API CRDs and Traefik, called by `deploy.sh` | [docs/gateway.md](../docs/gateway.md) |
