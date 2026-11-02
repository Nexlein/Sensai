# ADR-0003: Gateway API CRDs and Traefik installed outside the chart, host-based routes on nip.io

- **Status:** Accepted
- **Date:** 2026-10-13
- **Deciders:** project team

## Context

[ADR-0001](0001-deployment-stack.md) chose Gateway API with Traefik as the single public entry point. Two questions were left open by issue #22:

- **Where does Traefik live?** As a dependency of the `bernstein` chart, or as a separate step before it.
- **How are `poll` and `result` told apart?** By host name or by path.

Constraints:

- **The evaluator's cluster is fresh.** Whatever we need must be installable by `deploy.sh` on any AKS.
- **CRDs and controllers are cluster-wide.** Helm installs CRDs from a chart's `crds/` folder once and never upgrades or deletes them; a controller shared by several releases must not be owned by one of them.
- **The Gateway needs the CRDs to exist when the chart is installed**, or `helm install` fails with `no matches for kind "Gateway"`.
- **result serves its static assets and `/socket.io` from `/`.** A path prefix would need rewriting that the application does not expect.
- **No domain.** The public IP is only known once the load balancer exists.

## Decision

1. **Prerequisites are a separate step**: `scripts/install-gateway.sh` applies the Gateway API CRDs (standard channel, pinned version) and installs the Traefik chart (pinned version, values in `infra/gateway/traefik-values.yaml`). `deploy.sh` (#23) calls it before `helm install`.
2. **The `Gateway` and the two `HTTPRoute`s belong to the `bernstein` chart**, in `templates/gateway/`: they describe this application and are upgraded with it.
3. **Routing is by host**: `poll.<domain>` and `result.<domain>`, with `<domain>` = `<public IP>.nip.io`, passed as `--set-string gateway.domain=...`. The script prints it.
4. **Without `gateway.domain` the chart renders no Gateway**, so `helm lint` and a plain `helm template` work without a cluster, and the apps stay reachable with `kubectl port-forward`.

Details in [gateway.md](../gateway.md).

## Alternatives

| Option | Why rejected |
| ------ | ------------ |
| Traefik as a chart dependency (subchart) | `helm uninstall bernstein` would remove the cluster's only entry point; the Gateway API CRDs still could not be a subchart template (Helm renders and validates everything in one pass, before the CRDs exist); the `traefik.*` keys would mix into our values and schema. |
| Gateway API CRDs in `crds/` | Helm never upgrades or deletes them, and the CRDs would belong to one application although every Gateway on the cluster uses them. |
| Path-based routes (`/poll`, `/result`) | Needs a URL rewrite, and result's assets and `/socket.io` are absolute paths from `/`: the page would load without its script. |
| A domain name and DNS record of our own | Costs money and a manual step on every cluster; the IP changes on every fresh cluster anyway. |
| `gateway.domain` required | `helm lint` and `helm template` (CI, #11) would need a fake domain, and the chart could not be installed before Traefik has an IP. |
| Two `Service type=LoadBalancer` | Rejected in #22: two billed public IPs, no layer 7 (no sticky cookie for #26). Kept as a fallback only. |

## Consequences

- Installation has two steps in a fixed order (CRDs and Traefik, then the chart); `deploy.sh` hides it, but a bare `helm install` of the chart on a fresh cluster serves nothing public until `gateway.domain` is set.
- Changing the public IP (new cluster) means a `helm upgrade` with the new domain: hostnames change, no pod restarts.
- HTTP only: no TLS, so credentials must never travel through this entry point. Adding it later means a certificate, a second listener and a real domain.
- nip.io is an external service: if it is down, hostnames do not resolve (`curl --resolve` or a `Host` header still work).
- We maintain two version pins (Gateway API, Traefik chart). We would revisit this decision if a second application used the cluster (then the Gateway moves out of the chart) or if TLS becomes a requirement.
