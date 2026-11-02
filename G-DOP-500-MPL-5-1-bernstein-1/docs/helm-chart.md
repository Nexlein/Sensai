# Helm chart

Walkthrough of `charts/bernstein/`: what each file is, what Helm does with it, and why it is written that way. For the short version (install command, values table), see the [chart README](../charts/bernstein/README.md). Why Helm was chosen over Kustomize or raw manifests is recorded in [ADR-0001](adr/0001-deployment-stack.md).

## How Helm uses the chart

**Helm** is a package manager for Kubernetes. A **chart** is a folder describing an application as templates plus settings. On `helm install` / `helm upgrade`, Helm runs these steps in order:

```
values.yaml (defaults)
   + overrides (--set ..., -f file.yaml)
   → merged "values"
   → checked against values.schema.json      ← stops here if something is wrong
   → every file in templates/ is rendered    ← templates call the helpers in _helpers.tpl
   → the resulting YAML manifests are sent to Kubernetes
   → NOTES.txt is rendered and printed
```

The chart was scaffolded by #14, the parent of the component issues. It provides the frame: shared settings, shared helpers, validation and folder layout. The Kubernetes objects themselves (Deployments, StatefulSets, Services, ...) are added by #15–#22; see [Which issue fills what](#which-issue-fills-what).

## Layout

```
charts/bernstein/
├── Chart.yaml            identity card of the chart
├── values.yaml           default settings
├── values.schema.json    rules the settings must follow
├── files/
│   └── schema.sql        copy of the application's schema, read by the ConfigMap
├── .helmignore           files Helm must not load
├── README.md             short usage documentation
└── templates/
    ├── _helpers.tpl      reusable template functions
    ├── NOTES.txt         message printed after install
    ├── poll/             one folder per component
    │   ├── deployment.yaml   2 poll pods
    │   ├── hpa.yaml          autoscaler, 2 to 5 pods
    │   ├── pdb.yaml          at least 1 pod during a drain
    │   └── service.yaml      poll:80
    ├── worker/
    ├── result/
    │   ├── deployment.yaml   1 result pod
    │   ├── hpa.yaml          autoscaler, off until sticky sessions (#26)
    │   └── service.yaml      result:80
    ├── namespace/
    │   ├── limitrange.yaml   defaults for containers without requests or limits
    │   └── resourcequota.yaml  cap on the namespace's total usage
    ├── redis/
    │   ├── secret.yaml       Redis password, generated once
    │   ├── statefulset.yaml  Redis 8 pod and its data disk
    │   └── service.yaml      redis:6379, and the headless Service
    └── postgres/
        ├── secret.yaml       PostgreSQL password, given at deploy time
        ├── statefulset.yaml  PostgreSQL 18 pod and its data disk
        ├── initdb-configmap.yaml  schema.sql run by postgres at its first start
        ├── schema-configmap.yaml  schema.sql as a file (hook)
        ├── schema-job.yaml   applies it before upgrade (hook)
        └── service.yaml      postgres:5432, and the headless Service
```

Each component has its own document, covering everything the chart deploys for it: [poll.md](poll.md), [result.md](result.md), [postgres.md](postgres.md), [redis.md](redis.md).

## `Chart.yaml`

Mandatory file: Helm reads it to know what the chart is.

```yaml
apiVersion: v2
name: bernstein
description: Poll application (...) for the Bernstein project.
type: application
version: 0.1.0
appVersion: "dev"
```

| Field | Meaning |
|---|---|
| `apiVersion: v2` | Chart format of Helm 3 and 4 (`v1` was Helm 2). |
| `name: bernstein` | Chart name, reused in labels (`app.kubernetes.io/name: bernstein`, `helm.sh/chart: bernstein-0.1.0`). |
| `type: application` | An installable chart. The other type, `library`, only provides helpers and cannot be installed. |
| `version: 0.1.0` | Version of the **chart itself** (templates, values, schema). Bump it on every chart change. |
| `appVersion: "dev"` | Version of the **application** inside. Shown in the APP VERSION column of `helm list` and `helm history`. |

`appVersion` is a placeholder. Setting it to the deployed git SHA requires `helm package --app-version <sha>`: `helm upgrade` has no such flag, and installing straight from the folder (`helm upgrade --install charts/bernstein`) uses the file as is. Whether the deploy (#23) packages the chart is its decision. Labels do not depend on this field (see [`bernstein.labels`](helm-helpers.md#bernsteinlabels)).

## `values.yaml`

The chart's settings with their defaults. Templates read them as `.Values.<key>`; users override them with `--set key=value` or `-f file.yaml`, and overrides win.

### `global`: settings shared by every component

```yaml
global:
  registry: ""
  tag: ""
  imagePullPolicy: IfNotPresent
```

- **`registry`**: where our images live, e.g. `bernsteinacr.azurecr.io`. Empty on purpose: there is no sensible default (the evaluator may use their own registry), so it must be provided, and the schema enforces it.
- **`tag`**: image version, i.e. the git SHA pushed by CI (#12 uses immutable SHA tags). Empty on purpose, same reason.
- **`imagePullPolicy: IfNotPresent`**: a node downloads an image only if it does not have it yet. Safe because a SHA tag never points to different content. `Always` would contact the registry on every pod start: slower, and failing when the registry is unreachable.
- `global` is the usual Helm name for shared settings; Helm also passes it automatically to subcharts.

### Per-component `image` blocks

```yaml
poll:
  image:
    repository: poll
    tag: ""
```

Same for `worker` and `result`. Only `repository` is set; names match what CI pushes (`<acr>/poll:<sha>`, `<acr>/worker:<sha>`, `<acr>/result:<sha>`). An empty `tag` means "use `global.tag`". The key exists so a single component can be overridden, e.g. `--set worker.image.tag=abc123` to roll back only the worker.

### Redis and PostgreSQL

```yaml
redis:
  image:
    registry: docker.io
    repository: library/redis
    tag: "8.10.2"
    digest: sha256:2c2dff791878316e3b083188be0d578423b24813cdda5de0e80ea4f7b3e6bfd6
```

- They are official Docker Hub images, not ours, so they set their **own** `registry` instead of using `global.registry`.
- **`library/`** is Docker Hub's namespace for official images: `redis:8` is short for `docker.io/library/redis:8`. The full name is written because the image helper always builds `registry/repository:tag`.
- **`"8.10.2"` / `"18.6"` are quoted**: unquoted, YAML reads them as numbers, while a tag is text (and the schema expects a string).
- **`digest`**: a `sha256:...` digest points to one exact image, while a tag like `8` moves when Redis publishes a new 8.x. Both are pinned (`18.6` + digest, see [postgres.md](postgres.md#values); `8.10.2` + digest, see [redis.md](redis.md#values)).

### Shared database settings

```yaml
postgres:
  database: votes
  user: bernstein
```

Used by three components: the PostgreSQL container (the official image creates this database and user on first start), the worker and result (`POSTGRES_DB`, `POSTGRES_USER`). Defined once, so they cannot drift apart.

### Passwords

```yaml
redis:
  existingSecret: ""
postgres:
  password: ""
  existingSecret: ""
```

- **`postgres.password`** stays empty in the file: the subject forbids it in the repository. It is given at deploy time with `--set-string postgres.password="$POSTGRES_PASSWORD"`, and the chart refuses to render without it.
- **`existingSecret`**: name of a Secret created beforehand, with a `password` key; the chart then creates no Secret and uses that one.
- **Redis has no password value**: the chart generates it, since only Redis, poll and the worker need it.

Details in [postgres.md](postgres.md#password) and [redis.md](redis.md#password); what both have in common in [Passwords](#passwords).

## `values.schema.json`

A [JSON Schema](https://json-schema.org/) (draft-07). Helm checks the final merged values against it on `install`, `upgrade`, `template` and `lint`, **before contacting the cluster**, and stops on the first broken rule.

Without it, an empty registry renders the image `/poll:`: Kubernetes accepts the manifest, pods fail with `InvalidImageName` / `ImagePullBackOff`, and with `--atomic --timeout 10m` the failure only shows after 10 minutes. With it, the error is immediate:

```text
Error: INSTALLATION FAILED: values don't meet the specifications of the schema(s) in the following chart(s):
bernstein:
- at '/global/registry': minLength: got 0, want 1
```

### Rules

| Rule | Why |
|---|---|
| `global` requires `registry` and `tag` | The two keys must exist. |
| `minLength: 1` on both | `required` alone is not enough: `values.yaml` defines `registry: ""`, so the key always exists. `minLength` rejects the empty string. |
| `registry` pattern `^[A-Za-z0-9.-]+(:[0-9]+)?(/[a-z0-9._-]+)*$` | Hostname, optional `:port`, optional `/path` segments. Rejects `https://x.io/`, which would produce `https://x.io//poll`. |
| `tag` pattern `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$` | Docker's tag grammar: up to 128 characters of letters, digits, `_`, `.`, `-`, not starting with `.` or `-`. |
| `imagePullPolicy` enum | Only the three values Kubernetes accepts. |
| `definitions.image` with `additionalProperties: false` | Typos such as `respository` are refused instead of silently ignored. |
| `digest` pattern `^(sha256:[a-f0-9]{64})?$` | Empty, or a real sha256 digest. |
| `redis` / `postgres` with `allOf` | "A normal component" plus their own keys: `database` and `user` as non-empty strings, `password`, `existingSecret`. |
| `existingSecret` (`definitions.secretName`) | Empty, or a valid Kubernetes object name: lowercase letters, digits, `-` and `.`, at most 253 characters. `Bad_Name` is rejected here rather than by Kubernetes mid-deploy. |
| `postgres.persistence`: `size` pattern `^[1-9][0-9]*(Mi\|Gi\|Ti)$`, `storageClass` an object name or empty, no other key | A size Kubernetes understands (`5Gi`, not `5G` or `5 GB`), and typos such as `storageclass` refused. |

`definitions` + `$ref` let the five components share one definition. `global` and the top level are left **open** (no `additionalProperties: false`) so component issues can add keys; each new key should still be added to the schema.

The schema does not require `postgres.password`: "password **or** existingSecret" needs an `anyOf`, whose error does not say what to do. The Secret template checks it instead, with a message giving the command ([postgres.md](postgres.md#templatespostgressecretyaml)).

Consequences:

- A bare `helm lint charts/bernstein` fails, since lint validates the schema and renders the templates. CI (#11) must pass `global.registry`, `global.tag` and `postgres.password`.
- Pass the tag with **`--set-string`**: `--set global.tag=1234567` turns an all-digit short SHA into a number, rejected with `got number, want string`.

## `templates/_helpers.tpl`

Named, reusable template snippets: defined once with `define`, called from every manifest with `include`, so all objects get identical labels and image references. A file whose name starts with `_` produces no Kubernetes object. Every helper takes the root context and the component name: `(dict "context" $ "component" "poll")`.

| Helper | Output | Used for |
|---|---|---|
| `bernstein.labels` | `helm.sh/chart`, `app.kubernetes.io/{name,instance,component,version,managed-by}` | `metadata.labels` of every object and pod template |
| `bernstein.selectorLabels` | `app.kubernetes.io/{name,instance,component}` | `spec.selector` and Services |
| `bernstein.image` | `<registry>/<repository>:<tag>[@<digest>]`, defaulting to `global.registry` / `global.tag` | container `image:` |
| `bernstein.chart` | `bernstein-0.1.0` | the `helm.sh/chart` label |
| `bernstein.secretName` | `<component>.existingSecret`, else `<component>-credentials` | the password Secret's name, in the Secret and in every `secretKeyRef` |
| `bernstein.secretChecksum` | SHA-256 fingerprint of a component's password | `checksum/<component>-secret` pod annotation |

Key choices:

- Selector labels are a separate, stable subset because a Deployment's selector is immutable: a version in it would make every upgrade fail with `field is immutable`.
- `app.kubernetes.io/version` is the tag the component runs: its own image tag (`8.10.2` for Redis, `18.6` for PostgreSQL) or else `global.tag`.
- `name` is the chart name (`bernstein`) and `component` tells pods apart; `part-of` is left out because it would duplicate `name`.

What a helper is, the Go template syntax, and every line of this file: [helm-helpers.md](helm-helpers.md).

## `templates/NOTES.txt`

Rendered like a template but **not sent to Kubernetes**: Helm prints it after `install` / `upgrade`, and again on `helm status`. It can use `{{ .Release.Namespace }}` etc., so the printed commands are ready to copy and paste.

1. **Watch the pods** until Ready, filtered by the `instance` label.
2. **Get the external URLs**: read the public IP from the Gateway's `status.addresses`, then build `poll.<IP>.nip.io` and `result.<IP>.nip.io`. [nip.io](https://nip.io) is a free wildcard DNS service (`poll.1.2.3.4.nip.io` resolves to `1.2.3.4`), giving host-based routing without buying a domain.
3. **Port-forward fallback** to reach the poll and result Services from a workstation without the Gateway.
4. **History and rollback** commands.

Step 2 matches the Gateway of #22 ([gateway.md](gateway.md)): it lives in the release namespace and Traefik copies the load balancer IP into its `status.addresses`. It only works when the release was installed with `gateway.domain`; otherwise use step 3.

## `templates/<component>/`

One folder per component, named like its key in `values.yaml`. Each component's manifests go in its folder.

**Git does not track empty folders**, so each one initially holds an empty `.gitkeep` file (a convention, not a Git feature). It is deleted once the folder has real files, as in `redis/` and `postgres/`.

## Passwords

What the PostgreSQL and Redis passwords have in common. Each component's specifics are in [postgres.md](postgres.md#password) and [redis.md](redis.md#password).

| Password | Secret | Where it comes from |
|---|---|---|
| PostgreSQL | `postgres-credentials` | given at deploy time: `--set-string postgres.password="$POSTGRES_PASSWORD"` |
| Redis | `redis-credentials` | generated by the chart on first install, kept on upgrades |

Either can instead come from a Secret created beforehand (`<component>.existingSecret`).

### Secrets

A Kubernetes **Secret** is an object holding sensitive values, base64-encoded under `data`. **Base64 is an encoding, not encryption**: anyone allowed to read Secrets in the namespace can decode them. What a Secret brings is separation: the value stays out of the Deployment manifests and logs, and RBAC can let someone manage pods without reading Secrets.

Containers receive the password as an environment variable read from the Secret, so the value never appears in their manifest:

```yaml
env:
  - name: POSTGRES_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ include "bernstein.secretName" (dict "context" $ "component" "postgres") }}
        key: password
```

### Restarting pods when a password changes

Environment variables are read **when the container starts**: updating a Secret does not reach running pods. Every workload reading a password therefore puts its fingerprint in a pod template annotation:

```yaml
template:
  metadata:
    annotations:
      checksum/postgres-secret: {{ include "bernstein.secretChecksum" (dict "context" $ "component" "postgres") }}
```

A new password changes the annotation, so the pod template changes, and Kubernetes rolls the pods with the same rolling update as a new image. The annotation has no other effect. How the fingerprint is computed, and why the generated Redis password gets a constant one: [helm-helpers.md](helm-helpers.md#bernsteinsecretchecksum).

### Where a password ends up

- **In its Secret**, readable by whoever can read Secrets in the namespace.
- **In Helm's release record**: Helm stores each revision (the values given with `--set`, and the rendered manifests, Secrets included) in a Secret named `sh.helm.release.v1.<release>.v<revision>` in the same namespace. Same audience as above.
- **As a hash in the pod annotation**, readable by anyone allowed to get pods. A SHA-256 cannot be reversed, but a short password can be guessed offline by hashing candidates. Hence the advice to use a long random password, e.g. `openssl rand -base64 32`.
- **Never in the repository**: `postgres.password` is empty in `values.yaml`, and the deploy reads it from an environment variable.

## `.helmignore`

Like `.gitignore`, but for Helm: matching files are skipped when Helm loads or packages the chart (`install` from the folder, `lint`, `package`). It is the default generated by `helm create` (VCS folders, backup files, IDE folders), trimmed of tools we do not use, plus **`.gitkeep`**: Helm only expects `.yaml`, `.yml`, `.tpl` or `.txt` files in `templates/`, so the placeholders are never loaded.

## `README.md`

Short documentation shown by `helm show readme`: install command, `--set-string` and `--atomic`, history/rollback, the schema error, local checks, values table, layout, and an example Deployment showing where each helper goes. Not used to render anything.

## Verifying the chart

From the repository root, in the Nix dev shell:

```sh
OK="--set global.registry=example.azurecr.io --set-string global.tag=dev --set-string postgres.password=dev"

# Must pass
helm lint --strict charts/bernstein $OK
helm template bernstein charts/bernstein $OK

# Must fail with a schema error
helm template bernstein charts/bernstein --set-string global.tag=dev        # no registry
helm template bernstein charts/bernstein --set global.registry=https://x.io/ --set-string global.tag=dev
helm template bernstein charts/bernstein --set global.registry=x.io --set global.tag=1234567  # number
helm template bernstein charts/bernstein $OK --set poll.image.respository=x  # typo
helm template bernstein charts/bernstein $OK --set postgres.existingSecret=Bad_Name

# Must fail with "postgres.password is required"
helm template bernstein charts/bernstein --set global.registry=x.io --set-string global.tag=dev

# Print NOTES.txt without a cluster
helm install bernstein charts/bernstein $OK -n bernstein --dry-run=client

# Manifests valid against the Kubernetes 1.36 API (kubeconform is not in the dev shell)
helm template bernstein charts/bernstein $OK | nix shell nixpkgs#kubeconform -c kubeconform -strict -summary -kubernetes-version 1.36.0
```

To check the helpers while no component template exists, copy the chart outside the repository and add a throwaway template that calls them:

```yaml
{{- range $c := list "poll" "worker" "result" "redis" "postgres" }}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $c }}-test
  labels:
    {{- include "bernstein.labels" (dict "context" $ "component" $c) | nindent 4 }}
data:
  image: {{ include "bernstein.image" (dict "context" $ "component" $c) | quote }}
{{- end }}
```

## Testing on a local cluster

`helm template` and `kubeconform` only prove that the manifests are valid. Whether PostgreSQL actually starts, keeps its data or accepts its password needs a cluster. A local [kind](https://kind.sigs.k8s.io/) cluster (Kubernetes in a Docker container) answers that for free, without starting AKS (0.31 €/h).

```sh
KC=/tmp/bernstein-kind.kubeconfig     # separate kubeconfig: your current context is left alone
nix shell nixpkgs#kind -c kind create cluster --name bernstein-test --kubeconfig "$KC" --wait 180s

helm install bernstein charts/bernstein --kubeconfig "$KC" -n bernstein --create-namespace \
  --set global.registry=example.azurecr.io --set-string global.tag=dev \
  --set-string postgres.password=dev \
  --set postgres.persistence.storageClass= --set redis.persistence.storageClass=   # kind has no managed-csi: use its default class (both disks, or redis-0 stays Pending)
kubectl --kubeconfig "$KC" -n bernstein wait --for=condition=Ready pod/postgres-0 --timeout=300s

nix shell nixpkgs#kind -c kind delete cluster --name bernstein-test --kubeconfig "$KC"
```

- `--kubeconfig` keeps kind from adding its cluster to `~/.kube/config` and switching the current context, which may point at AKS.
- kind runs the same Kubernetes version as AKS (1.36), but not Azure: no `managed-csi`, no load balancer, and its volumes are plain directories that ignore `fsGroup`. Those parts are checked on AKS.
- Images from our ACR cannot be pulled without credentials; components built from them are tested once CI pushes images (#12).

The checks run this way are listed in each component's document (e.g. [postgres.md](postgres.md#verifying)).

## Which issue fills what

| Piece | Issue |
|---|---|
| `templates/postgres/`: StatefulSet, Services, PVC ([postgres.md](postgres.md)) | #15, done |
| Schema job applying `schema.sql` ([postgres.md](postgres.md#schema)) | #16, done |
| Database and Redis passwords: Secrets, `existingSecret`, secret helpers ([Passwords](#passwords)) | #17, done |
| `templates/poll/`: Deployment, Service ([poll.md](poll.md)) | #19, done |
| `templates/redis/`: StatefulSet, Services ([redis.md](redis.md)) | #18, done |
| `templates/worker/`: Deployment ([worker.md](worker.md)) | #20, done |
| `templates/result/`: Deployment, Service ([result.md](result.md)) | #21, done |
| `templates/gateway/`: Gateway, HTTPRoutes, and NOTES step 2 ([gateway.md](gateway.md)) | #22, done |
| Deploy script, `appVersion` set to the git SHA | #23 |
| `helm lint` / `helm template` in CI | #11 |

Update this document, and the component's own document ([postgres.md](postgres.md), [redis.md](redis.md), ...), when these land. Workloads reading a password use the secret helpers as shown in [Passwords](#passwords).
