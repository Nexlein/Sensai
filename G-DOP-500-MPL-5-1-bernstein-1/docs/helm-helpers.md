# Helm helpers

What a Helm helper is, the template syntax it uses, and `charts/bernstein/templates/_helpers.tpl` explained line by line. For an overview of every file in the chart, see [helm-chart.md](helm-chart.md).

## What a helper is

A **helper** is a named piece of template text, written once and reused everywhere: a function whose return value is text (YAML).

- **`define`** creates it: `{{- define "bernstein.labels" -}} ...text... {{- end }}`
- **`include`** calls it and returns its text: `{{ include "bernstein.labels" ... }}`

The chart will hold 15–20 objects (a Deployment and a Service per app, StatefulSets, PodDisruptionBudgets #28, NetworkPolicies #32), all needing the same labels and image logic. Copied by hand, the same six label lines would live in 20 files: changing one label means 20 edits, and **a single typo silently breaks traffic**. A Service finds its pods by labels: if the Service says `component: poll` and the pods say `component: pol`, it has no endpoints and the page is down, without any error. With a helper there is one definition, so every object gets identical text.

Helm turns every file in `templates/` into Kubernetes objects, **except files starting with `_`**. `_helpers.tpl` only defines snippets, so it never produces an object by itself.

### Before / after

Without a helper, the poll Deployment would repeat this block in its metadata, its pod template, its Service, its PDB, ...:

```yaml
metadata:
  labels:
    helm.sh/chart: bernstein-0.1.0
    app.kubernetes.io/name: bernstein
    app.kubernetes.io/instance: {{ .Release.Name }}
    app.kubernetes.io/component: poll
    app.kubernetes.io/version: {{ .Values.global.tag | quote }}
    app.kubernetes.io/managed-by: {{ .Release.Service }}
```

With the helper:

```yaml
metadata:
  labels:
    {{- include "bernstein.labels" (dict "context" $ "component" "poll") | nindent 4 }}
```

Both render to:

```yaml
metadata:
  labels:
    helm.sh/chart: bernstein-0.1.0
    app.kubernetes.io/name: bernstein
    app.kubernetes.io/instance: bernstein
    app.kubernetes.io/component: poll
    app.kubernetes.io/version: "96ea37d"
    app.kubernetes.io/managed-by: Helm
```

## Template syntax

Helm templates are [Go templates](https://pkg.go.dev/text/template) plus the functions of the [Sprig](https://masterminds.github.io/sprig/) library.

| Syntax | Meaning |
|---|---|
| `{{ ... }}` | An action: computes something, and prints it if it produces a value. |
| `.` | The current object. In a normal template it is the root (`.Values`, `.Release`, `.Chart`); inside a helper it is **whatever was passed in**. |
| `$` | Always the root, wherever you are. |
| `a \| f b` | Pipe: the left value becomes the **last argument** of `f`. `x \| default y` means `default y x`. |
| `$x := ...` | Creates a variable; `$x = ...` changes an existing one. |
| `{{-` / `-}}` | Trims whitespace and newlines before / after the action, so the YAML gets no stray blank lines. |
| `{{/* ... */}}` | Comment, never printed. |

## `_helpers.tpl` line by line

Examples below use release name `bernstein`, chart version `0.1.0` and `global.tag=96ea37d`.

### Calling convention

```
{{/*
Every helper below takes a dict with the root context and the component name, ...
  {{ include "bernstein.labels" (dict "context" $ "component" "poll") }}
*/}}
```

A helper receives **one single argument**, but ours need two things: the **root** (`$`), to read `.Values`, `.Release` and `.Chart`, and the **component name**. `dict "context" $ "component" "poll"` packs both into a small map, `{context: <root>, component: "poll"}`, read back inside the helper as `.context` and `.component`.

The component name is also the key under `.Values` and the folder under `templates/`, so one word identifies everything.

### `bernstein.chart`

```
{{- define "bernstein.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}
```

A chain read left to right:

1. `printf "%s-%s" .Chart.Name .Chart.Version` fills the two `%s`: `"bernstein-0.1.0"`. `.Chart` is the content of `Chart.yaml`.
2. `| replace "+" "_"`: a version may contain `+` (`1.0.0+build5`), which is **forbidden** in label values.
3. `| trunc 63`: label values are limited to 63 characters.
4. `| trimSuffix "-"`: a label must end with a letter or digit, so a `-` left by the cut is removed.

This helper is called with `.context` (see `bernstein.labels`), so here `.` *is* the root: hence `.Chart.Name`, not `.context.Chart.Name`.

### `bernstein.selectorLabels`

```
{{- define "bernstein.selectorLabels" -}}
app.kubernetes.io/name: {{ .context.Chart.Name }}
app.kubernetes.io/instance: {{ .context.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}
```

Here `.` is the dict, so the root is reached through `.context`.

| Label | Source | Value |
|---|---|---|
| `name` | `Chart.yaml` → `name:` | `bernstein` |
| `instance` | release name given on the command line: `helm install `**`bernstein`**` charts/...` | `bernstein` |
| `component` | the dict | `poll` |

**Why a separate helper:** a Deployment's `spec.selector.matchLabels` **can never be changed** after creation. If it contained `version`, every upgrade (new SHA) would try to change it and Kubernetes would refuse with `field is immutable`. Selectors get these three stable labels only; the full set goes on `metadata.labels`.

- `instance`: two releases in the same namespace never select each other's pods.
- `component`: separates poll pods from result pods; without it, the `poll` Service would also send traffic to result pods.

### `bernstein.labels`

```
{{- define "bernstein.labels" -}}
{{- $version := dig .component "image" "tag" "" .context.Values.AsMap | default .context.Values.global.tag -}}
helm.sh/chart: {{ include "bernstein.chart" .context }}
{{ include "bernstein.selectorLabels" . }}
app.kubernetes.io/version: {{ $version | trunc 63 | trimSuffix "-" | quote }}
app.kubernetes.io/managed-by: {{ .context.Release.Service }}
{{- end }}
```

The [recommended Kubernetes labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/), for the `metadata.labels` of every object and pod template. They enable `kubectl get pods -l app.kubernetes.io/component=poll`, and NetworkPolicies and PDBs select pods with them.

**The `$version` line**, step by step:

1. `.context.Values.AsMap` turns the values into a plain map. `.Values` is Helm's own type and `dig` refuses it: without `.AsMap`, rendering fails with `interface conversion: interface {} is common.Values, not map[string]interface {}`.
2. `dig "poll" "image" "tag" "" <map>`: go into `poll`, then `image`, then `tag`, and return `""` if anything on the way is missing. A safe nested lookup that never crashes.
   - poll → `""` (empty in `values.yaml`), redis → `"8"`, a future `gateway` without values → `""`.
3. `| default .context.Values.global.tag`: if the result is empty, use `global.tag`.
   - poll → `"96ea37d"`, redis → `"8"`, postgres → `"18"`.
4. `$version := ...` stores the result and prints **nothing**. The closing `-}}` also removes the newline after the action. Without it, the helper's output would start with that newline, and every `labels:` block would render with an empty line first:

   ```yaml
     labels:

       helm.sh/chart: bernstein-0.1.0
   ```

**`helm.sh/chart: {{ include "bernstein.chart" .context }}`**: plain text followed by another helper's output, giving `helm.sh/chart: bernstein-0.1.0`.

**`{{ include "bernstein.selectorLabels" . }}`**: passes **the same dict** along, printing the three selector labels. They are written only once in the chart, so selector and labels can never disagree.

**`app.kubernetes.io/version: {{ $version | trunc 63 | trimSuffix "-" | quote }}`**: same 63-character safety, then `quote` wraps the value in `"..."`. Unquoted, `18` would be read as the **number** 18, which Kubernetes rejects as a label value.

**`app.kubernetes.io/managed-by: {{ .context.Release.Service }}`**: always `"Helm"`, telling anyone looking at the cluster which tool owns the object.

`name` is the chart name (`bernstein`) rather than `poll`, as in Helm's own conventions; `component` does the distinguishing. `app.kubernetes.io/part-of` is left out because it would duplicate `name`.

### `bernstein.image`

```
{{- define "bernstein.image" -}}
{{- $values := index .context.Values .component | required (printf "values: %s is missing" .component) }}
{{- $image := $values.image | required (printf "values: %s.image is missing" .component) }}
{{- $repository := $image.repository | required (printf "values: %s.image.repository is required" .component) }}
{{- $global := .context.Values.global }}
{{- $ref := printf "%s/%s:%s" ($image.registry | default $global.registry) $repository ($image.tag | default $global.tag) }}
{{- if $image.digest }}
{{- $ref = printf "%s@%s" $ref $image.digest }}
{{- end }}
{{- $ref }}
{{- end }}
```

**`index .context.Values .component`** is `.Values["poll"]`. `.Values.poll` cannot be written because the name is **in a variable**; `index` looks up a key held in a variable.

**`| required "message"`**: if the result is empty, Helm **stops** and prints the message. A typo such as `"component" "pol"` gives `values: pol is missing` instead of a cryptic nil error. The next two lines do the same one level deeper, for `.image` and `.image.repository`.

**`$global := .context.Values.global`**: a shortcut, so the next line does not repeat `.context.Values.global`.

**The `$ref := printf ...` line** fills `registry/repository:tag`; the parentheses compute each fallback before `printf` uses it:

| Placeholder | poll | redis |
|---|---|---|
| registry: `$image.registry \| default $global.registry` | empty → `bernsteinacr.azurecr.io` | `docker.io` |
| repository | `poll` | `library/redis` |
| tag: `$image.tag \| default $global.tag` | empty → `96ea37d` | `8` |
| **Result** | `bernsteinacr.azurecr.io/poll:96ea37d` | `docker.io/library/redis:8` |

**`if $image.digest`** → **`$ref = ...`**: `=`, not `:=`, because it **changes** `$ref`. Postgres with a pinned digest becomes `docker.io/library/postgres:18@sha256:...`. With both tag and digest, the container runtime pulls by digest; the tag is only a readable hint.

**`{{- $ref }}`** is the only line that prints anything. Everything above only computes variables; this outputs the final string, which is what `include` returns.

### `bernstein.secretName`

```
{{- define "bernstein.secretName" -}}
{{- $values := index .context.Values .component | required (printf "values: %s is missing" .component) }}
{{- $values.existingSecret | default (printf "%s-credentials" .component) }}
{{- end }}
```

Name of the Secret holding a component's password (postgres, redis): the user's own Secret if `<component>.existingSecret` is set, else `<component>-credentials`, the one the chart creates.

| Values | postgres | redis |
|---|---|---|
| defaults | `postgres-credentials` | `redis-credentials` |
| `--set postgres.existingSecret=pg-auth` | `pg-auth` | `redis-credentials` |

The Secret template and every pod reading the password call this helper, so the name exists in one place: the Secret and its readers cannot disagree. `$values` is a plain map (it comes from `index`), so `$values.existingSecret` works directly, without the `.AsMap` that `dig` needs on `.Values`.

### `bernstein.secretChecksum`

```
{{- define "bernstein.secretChecksum" -}}
{{- $values := index .context.Values .component | required (printf "values: %s is missing" .component) }}
{{- if $values.existingSecret }}
{{- (lookup "v1" "Secret" .context.Release.Namespace $values.existingSecret).data | default dict | toJson | sha256sum }}
{{- else }}
{{- $values.password | default "generated" | sha256sum }}
{{- end }}
{{- end }}
```

A fingerprint of a component's password, for an annotation on the pod template of every workload that reads it. Environment variables from a Secret are only read when a container starts, so a new password does not reach running pods by itself. A new password changes this value, hence the pod template, and Kubernetes rolls the pods, exactly as for a new image. Why and where it is used: [helm-chart.md](helm-chart.md#restarting-pods-when-a-password-changes).

`sha256sum` turns any text into a fixed 64-character hexadecimal hash: the same input always gives the same hash, a different input a different one. Three cases:

| Case | Input of the hash | Changes when |
|---|---|---|
| `existingSecret` set | that Secret's current `data`, read from the cluster | its content changes |
| password from values (postgres) | `postgres.password` | a new password is deployed |
| generated password (redis) | the constant `"generated"` | never |

- **`lookup "v1" "Secret" <namespace> <name>`** reads an object from the cluster. Wrapped in parentheses so that `.data` can be taken from its result.
- **`| default dict`**: without a cluster (`helm template`), or if the Secret does not exist, `.data` is empty; `default dict` turns it into an empty map, so `toJson` always gets a map.
- **`| toJson`**: turns the map into text, `{"password":"..."}`, with keys in sorted order, so the same content always gives the same text and the same hash.
- **`$values.password | default "generated"`**: redis has no `password` key, so it falls back to the constant.

**Why the generated password is not hashed:** hashing the redis Secret's content would hash a random value at install (lookup finds nothing, so a new password is generated for the hash) and the stored one on the first upgrade. The hash would change once, and every pod reading the password would restart for nothing. The generated password never changes, so a constant is correct. If someone deletes `redis-credentials`, the pods must be restarted by hand ([redis.md](redis.md#if-redis-credentials-is-deleted)).

### `bernstein.env.redis` and `bernstein.env.postgres`

```
{{- define "bernstein.env.redis" -}}
- name: REDIS_HOST
  value: redis
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "bernstein.secretName" (dict "context" .context "component" "redis") }}
      key: password
{{- end }}
```

`bernstein.env.postgres` has the same shape with `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` (from `postgres.database` and `postgres.user`) and `POSTGRES_PASSWORD`.

Two components read Redis (poll, worker) and two read PostgreSQL (worker, result). Written in each Deployment, the same seven lines existed in two places and could drift: a renamed Service or Secret key fixed in one and forgotten in the other would only fail at runtime. The helpers hold them once.

- **The output is a list of items, not a whole `env:`.** The Deployment keeps `env:` and can mix the helpers with its own entries (poll adds `OPTION_A` to `OPTION_D`; the worker uses both helpers).
- **They take the root context alone**, `(dict "context" $)`: no component is needed, the helper knows which password it reads. This is the one exception to the `"component"` key of the calling convention.
- **They call `bernstein.secretName`** with `"redis"` or `"postgres"`, so the Secret name is still computed in one place.
- **Pair them with the checksum annotation** of the same password (`checksum/redis-secret`, `checksum/postgres-secret`): the helper gives the variables, the annotation rolls the pods when the password changes.

Used as:

```
          env:
            {{- include "bernstein.env.redis" (dict "context" $) | nindent 12 }}
            {{- include "bernstein.env.postgres" (dict "context" $) | nindent 12 }}
```

which renders, for the worker:

```yaml
          env:
            - name: REDIS_HOST
              value: redis
            - name: REDIS_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: redis-credentials
                  key: password
            - name: POSTGRES_HOST
              value: postgres
            ...
```

The rendered output of poll and result was compared before and after moving their variables into the helpers: identical.

### `bernstein.hpa`

```
{{- define "bernstein.hpa" -}}
{{- $values := index .context.Values .component | required (printf "values: %s is missing" .component) }}
{{- $hpa := $values.autoscaling }}
{{- if $hpa.enabled }}
{{- if lt (int $hpa.maxReplicas) (int $hpa.minReplicas) }}
{{- fail (printf "values: %s.autoscaling.maxReplicas (%v) is below minReplicas (%v)" .component $hpa.maxReplicas $hpa.minReplicas) }}
{{- end }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
...
```

Renders the whole HorizontalPodAutoscaler of a Deployment. `templates/poll/hpa.yaml` and `templates/result/hpa.yaml` are each one line: `{{- include "bernstein.hpa" (dict "context" $ "component" "poll") }}`. The two autoscalers are identical except for the name and the values, so one definition avoids two files that drift.

- **`index .context.Values .component`** reads `.Values.poll` or `.Values.result` from the component name, as `bernstein.image` does.
- **`if $hpa.enabled`**: when false the helper outputs nothing, so the file renders empty and Helm skips it. This is how `result` ships with the autoscaler off.
- **`fail`**: the JSON schema checks each number alone but cannot compare two of them. `maxReplicas` below `minReplicas` would be refused by the API server at install with a less readable error; `fail` stops `helm template` first:

```text
Error: execution error at (bernstein/templates/poll/hpa.yaml:1:4): values: poll.autoscaling.maxReplicas (1) is below minReplicas (2)
```

- **`int`** converts both values before `lt`: a number read from YAML may be a float64 in Go templates, and `lt` refuses to compare mixed types.
- **`bernstein.labels`** is called with the same `.` (the dict), so the HPA carries the usual labels.

### `bernstein.pdb` and `bernstein.topologySpread`

Same one-line-per-file pattern as `bernstein.hpa`: `templates/<component>/pdb.yaml` calls `bernstein.pdb`, and the three Deployments call `bernstein.topologySpread` under `topologySpreadConstraints:`. Both build their selector from `bernstein.selectorLabels`, so the budget and the spreading count exactly the pods of the Deployment. `bernstein.pdb` renders nothing for a single pod (`gt (int $pods) 1`), and reads the autoscaler's `minReplicas` with `dig "autoscaling" "enabled" false $values` so that the worker, which has no `autoscaling` key, does not fail on a nil. `topologySpread` returns a list that starts with a newline, hence `| trim | nindent 8` at the call site. Explained in [helm-availability.md](helm-availability.md).

The Deployment side: `{{- if not .Values.poll.autoscaling.enabled }}` around its `replicas:` line ([poll.md](poll.md#replicas-and-selector)).

## Using the helpers in a component template

A component template, e.g. `templates/poll/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: poll
  labels:
    {{- include "bernstein.labels" (dict "context" $ "component" "poll") | nindent 4 }}
spec:
  selector:
    matchLabels:
      {{- include "bernstein.selectorLabels" (dict "context" $ "component" "poll") | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "bernstein.labels" (dict "context" $ "component" "poll") | nindent 8 }}
      annotations:
        checksum/redis-secret: {{ include "bernstein.secretChecksum" (dict "context" $ "component" "redis") }}
    spec:
      containers:
        - name: poll
          image: {{ include "bernstein.image" (dict "context" $ "component" "poll") }}
          env:
            {{- include "bernstein.env.redis" (dict "context" $) | nindent 12 }}
```

- **`| nindent 4`**: the helper returns several unindented lines. `nindent 4` adds a **newline**, then **4 spaces in front of every line**, so they land under `labels:` (4 under `metadata`, 6 under `matchLabels`, 8 in the pod template). In YAML, wrong indentation means wrong structure.
- **`include`, not Go's built-in `template`**: `template` prints directly and cannot be piped, so `| nindent 4` would be impossible. `include` returns the text as a value that can be transformed.
- **The component passed is the one that owns the password**, not the one being deployed: poll reads Redis' password, so it calls the secret helpers with `"redis"`. Worker and result do the same with `"postgres"` (and the worker also with `"redis"`).
- **`valueFrom.secretKeyRef`** (inside `bernstein.env.redis`): the container gets the value of the Secret's `password` key as an environment variable. The password itself never appears in the Deployment.

## Seeing the output

Render the helpers with `helm template` and a throwaway template, as described in [Verifying the chart](helm-chart.md#verifying-the-chart).
