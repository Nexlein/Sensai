# Gateway

How poll and result are reached from the internet, and why it is built this way. Decision record: [ADR-0003](adr/0003-gateway-prerequisites-outside-chart.md).

## Role

```
browser --> <public IP>:80 --> Service traefik (LoadBalancer) --> Traefik pod --> Service poll:80   --> poll pods
                                                                              \-> Service result:80 --> result pods
```

One Azure load balancer and **one public IP** for both pages. Traefik (the Gateway API implementation) reads the `Host` header and picks the Service. The Services themselves stay `ClusterIP`, so nothing else is public ([cost.md](cost.md): each `LoadBalancer` Service would bill another IP).

## What we ship

| Object | File | Installed by |
|---|---|---|
| Gateway API CRDs v1.6.3, standard channel | applied from the upstream release | `scripts/install-gateway.sh` |
| Traefik (chart 41.7.1): controller, `GatewayClass traefik`, LoadBalancer Service | `infra/gateway/traefik-values.yaml` | `scripts/install-gateway.sh` |
| `Gateway` | `charts/bernstein/templates/gateway/gateway.yaml` | `helm install bernstein` |
| `HTTPRoute` poll, `HTTPRoute` result | `charts/bernstein/templates/gateway/httproute.yaml` | `helm install bernstein` |

The three Gateway API kinds split the roles: the **GatewayClass** names the implementation (cluster operator), the **Gateway** opens listeners (here one HTTP port), the **HTTPRoutes** attach hostnames to Services (application owner).

## Why the prerequisites are outside the chart

Fully argued in the ADR; short version: CRDs and the controller are cluster-wide, so they must not be owned (or removed) by one release, and the Gateway objects cannot be installed before their CRDs exist. The script is idempotent: `kubectl apply --server-side` and `helm upgrade --install`.

### `scripts/install-gateway.sh`

```bash
kubectl apply --server-side -f \
  "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml" >&2
```

`--server-side` because the CRDs are large: a client-side `apply` stores the whole object in the `last-applied-configuration` annotation and fails with `metadata.annotations: Too long` over 256 KiB. The standard channel holds the stable kinds (`GatewayClass`, `Gateway`, `HTTPRoute`, `GRPCRoute`); the experimental one (TCPRoute, ...) is not needed.

```bash
helm upgrade --install traefik traefik/traefik --version "${TRAEFIK_CHART_VERSION}" \
  --namespace "${NAMESPACE}" --create-namespace \
  --values "${root}/infra/gateway/traefik-values.yaml" --wait >&2
```

Pinned chart version, so a fresh cluster gets the same Traefik we tested. `--wait` returns once the Deployment is Ready **and** the LoadBalancer Service has an address.

The last lines poll `status.loadBalancer.ingress[0].ip` of the `traefik` Service and print `<ip>.nip.io` on **stdout**; everything else goes to stderr, so `DOMAIN=$(scripts/install-gateway.sh)` captures only the domain. [nip.io](https://nip.io) is a free wildcard DNS service: `poll.20.1.2.3.nip.io` resolves to `20.1.2.3`.

### `infra/gateway/traefik-values.yaml`

| Key | Why |
|---|---|
| `providers.kubernetesGateway.enabled: true` | Off by default: without it Traefik ignores Gateway API objects. |
| `gatewayClass.enabled: true` | Creates `GatewayClass traefik` (controller `traefik.io/gateway-controller`). |
| `gateway.enabled: false` | The chart would create its own Gateway in the `traefik` namespace; ours belongs to the application chart, next to its routes. |
| `ports.websecure.expose.default: false` | HTTP only: the Service exposes port 80 and no port 443 (one load-balancer rule, see the "≤ 5 rules" assumption in cost.md). |
| `ingressRoute.dashboard.enabled: false` | No dashboard exposed. |

## The chart part

Values (`gateway.*` in `values.yaml`, checked by `values.schema.json`):

| Value | Default | Meaning |
|---|---|---|
| `domain` | `""` | Suffix of the hostnames. Empty: **nothing in `templates/gateway/` is rendered**. |
| `className` | `traefik` | GatewayClass to use. |
| `port` | `8000` | Listener port. |

### `gateway.yaml`

```yaml
spec:
  gatewayClassName: traefik
  listeners:
    - name: http
      protocol: HTTP
      port: 8000
      allowedRoutes:
        namespaces:
          from: Same
```

`port: 8000` is Traefik's `web` entry point **inside the pod**; the Service maps 80 to it. A listener on a port that is not one of Traefik's entry points cannot receive traffic. `from: Same` lets only routes of the release's namespace attach (the default is the same, written down to make it visible).

### `httproute.yaml`

A `range` over `poll` and `result` renders one route each:

```yaml
spec:
  parentRefs:
    - name: gateway
  hostnames:
    - "poll.1.2.3.4.nip.io"
  rules:
    - backendRefs:
        - name: poll
          port: 80
```

No `matches`: a rule without any matches means "all paths", so the whole host goes to the Service. Host-based because result's assets and `/socket.io` are served from `/`; with path prefixes they would need a rewrite.

Websocket needs nothing: Traefik forwards the `Upgrade` header by default, and result's Socket.IO also falls back to long-polling. Rolling updates without dropped connections are #25.

### `traefikservice.yaml`: sticky sessions for result (#26)

Socket.IO opens each connection with HTTP long-polling and only then upgrades to a websocket. The handshake state (`sid`) lives in the memory of the pod that answered. Traefik balances requests round-robin, so with two result pods the second request lands on the other pod:

```
$ curl -H "Host: result.test.local" ".../socket.io/?EIO=4&transport=polling&sid=<sid>"
{"code":1,"message":"Session ID unknown"} -> 400
```

Measured on kind with two result pods, without the cookie: 8 handshakes, 8 times `400` (strict alternation). The browser loops on reconnecting and the scores never show.

The fix is a cookie that pins a browser to one pod. Gateway API has a standard field for it (`sessionPersistence` on a route rule) but it is not implemented by Traefik, so the `result` HTTPRoute points at a Traefik-specific object instead of the Service:

```yaml
apiVersion: traefik.io/v1alpha1
kind: TraefikService
metadata:
  name: result-sticky
spec:
  weighted:
    services:
      - name: result
        port: 80
        sticky:
          cookie:
            name: bernstein_result
            httpOnly: true
            sameSite: lax
```

```yaml
# httproute.yaml, result only
backendRefs:
  - group: traefik.io
    kind: TraefikService
    name: result-sticky
```

Three things that are easy to get wrong:

- **`sticky` goes on the service entry, not on `weighted`.** First attempt: `weighted.sticky.cookie`. The cookie was set (`bernstein_result=7e722e78415f50eb`, the same value for every client) but ignored: that level only chooses between the services of the list, and there is one, so there was nothing to pin. All follow-up requests still returned `400`. On the entry (a Kubernetes Service, which Traefik balances across pod IPs) the six clients tested got two different cookie values, one per pod, and 20 of 20 follow-up requests returned `200`.
- **Traefik must allow the cross-provider reference.** The route is read by the Gateway API provider and the TraefikService by the CRD provider; Traefik refuses that unless the route's namespace is in `providers.kubernetesGateway.crossProviderNamespaces` (Traefik ≥ 3.7.1, chart 41.7.1 ships 3.7.14). `infra/gateway/traefik-values.yaml` sets `bernstein`, and `install-gateway.sh` overrides it with `BERNSTEIN_NAMESPACE` (`deploy.sh` passes `NAMESPACE`). Traefik logs `Cross-provider references are restricted to namespaces [bernstein]` at start.
- **Traefik installed before #26 has no such setting.** `deploy.sh` skips the install when the GatewayClass exists, so on a cluster with an older Traefik run `scripts/install-gateway.sh` again (idempotent) or the result route is not accepted.

A client whose pod is gone (rollout) gets a pod that exists: a request with the old cookie after `kubectl rollout restart deploy/result` returned `200`, and Traefik issues a new cookie. Right after a rollout one request returned `502 Bad Gateway` before Traefik refreshed its endpoints; Socket.IO retries on its own. Closing that window is the job of #25 (readiness, `preStop`) and is measured by #27.

No Redis adapter is needed: each pod broadcasts the scores it reads from the database itself, so every pod emits the same data. Rejected: forcing `transports: ['websocket']` in the client (changes app code, loses the fallback behind proxies), `sessionAffinity: ClientIP` on the Service (behind the Gateway every request comes from Traefik's IP), `@socket.io/redis-adapter` (shares rooms, does not fix the polling handshake).

## Checked on a local cluster

kind has no load balancer, so the Service stays `<pending>`; the routing itself can still be checked through a port-forward and a `Host` header. With two nginx stand-ins named `poll` and `result`:

```
$ kubectl get gateway,httproute
NAME                                        CLASS     ADDRESS   PROGRAMMED   AGE
gateway.gateway.networking.k8s.io/gateway   traefik             True         5s

NAME                                         HOSTNAMES                   AGE
httproute.gateway.networking.k8s.io/poll     ["poll.1.2.3.4.nip.io"]     5s
httproute.gateway.networking.k8s.io/result   ["result.1.2.3.4.nip.io"]   5s

$ curl -s -o /dev/null -w '%{http_code}' -H "Host: poll.1.2.3.4.nip.io" localhost:8088/    # port-forward to svc/traefik
200
$ ... -H "Host: other.1.2.3.4.nip.io" ...
404
```

Both routes report `Accepted=True` and `ResolvedRefs=True`; an unknown host gets Traefik's 404. The remaining acceptance criteria (public `curl` returns 200, live vote updates in the browser, a single public IP) need the real AKS and are checked there.

## Traps

- **Gateway API kinds not found**: installing the chart before the CRDs gives `no matches for kind "Gateway" in version "gateway.networking.k8s.io/v1"`. Run `scripts/install-gateway.sh` first.
- **Nothing public after `helm install`**: `gateway.domain` was not set, so no Gateway was rendered. This is intended (see ADR); `NOTES.txt` shows the port-forward fallback.
- **Empty `ADDRESS` on the Gateway**: Traefik copies the Service's load-balancer address into the Gateway status; it stays empty while Azure provisions the IP (about a minute).
- **404 from Traefik**: the `Host` header does not match a route. `curl http://<ip>/` without a name always gives 404; use the `poll.<ip>.nip.io` name or `-H "Host: ..."`.
