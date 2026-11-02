{{/*
Every helper below takes a dict with the root context and the component name,
the same as the key under .Values and the folder under templates/:

  {{ include "bernstein.labels" (dict "context" $ "component" "poll") }}
*/}}

{{/*
Chart name and version, for the helm.sh/chart label.
*/}}
{{- define "bernstein.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Labels used in selectors: they must never change for the life of a release, so
version and chart are left out.
*/}}
{{- define "bernstein.selectorLabels" -}}
app.kubernetes.io/name: {{ .context.Chart.Name }}
app.kubernetes.io/instance: {{ .context.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Recommended app.kubernetes.io/* labels, to put on every object's metadata and on
pod templates. version is the tag the component runs: its own image tag (redis
"8", postgres "18") or else global.tag.
*/}}
{{- define "bernstein.labels" -}}
{{- $version := dig .component "image" "tag" "" .context.Values.AsMap | default .context.Values.global.tag -}}
helm.sh/chart: {{ include "bernstein.chart" .context }}
{{ include "bernstein.selectorLabels" . }}
app.kubernetes.io/version: {{ $version | trunc 63 | trimSuffix "-" | quote }}
app.kubernetes.io/managed-by: {{ .context.Release.Service }}
{{- end }}

{{/*
Image reference of a component, built from .Values.<component>.image:
<registry>/<repository>:<tag>[@<digest>], where registry defaults to
global.registry and tag to global.tag.
*/}}
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

{{/*
HorizontalPodAutoscaler of a Deployment (poll, result), from
.Values.<component>.autoscaling. Renders nothing when autoscaling.enabled is false.
Scales on CPU utilisation, a percentage of the container's CPU *request*, and waits
scaleDownStabilizationSeconds before removing pods so a short pause in the load
does not make the count flap. Needs metrics-server (shipped with AKS):

  {{- include "bernstein.hpa" (dict "context" $ "component" "poll") }}
*/}}
{{- define "bernstein.hpa" -}}
{{- $values := index .context.Values .component | required (printf "values: %s is missing" .component) }}
{{- $hpa := $values.autoscaling }}
{{- if $hpa.enabled }}
{{- if lt (int $hpa.maxReplicas) (int $hpa.minReplicas) }}
{{- fail (printf "values: %s.autoscaling.maxReplicas (%v) is below minReplicas (%v)" .component $hpa.maxReplicas $hpa.minReplicas) }}
{{- end }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ .component }}
  labels:
    {{- include "bernstein.labels" . | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ .component }}
  minReplicas: {{ $hpa.minReplicas }}
  maxReplicas: {{ $hpa.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ $hpa.targetCPUUtilizationPercentage }}
  behavior:
    scaleDown:
      stabilizationWindowSeconds: {{ $hpa.scaleDownStabilizationSeconds }}
{{- end }}
{{- end }}

{{/*
PodDisruptionBudget of a Deployment (poll, result, worker): at least one pod must stay
up during a voluntary disruption (kubectl drain, cluster upgrade, autoscaler
scale-down), so a drain evicts the pods of a component one after the other, never
all at once. Rendered only when the component runs more than one pod (the autoscaler's
minReplicas when it is on, else replicas): with a single pod the budget would forbid
every eviction and a drain would hang.

  {{- include "bernstein.pdb" (dict "context" $ "component" "poll") }}
*/}}
{{- define "bernstein.pdb" -}}
{{- $values := index .context.Values .component | required (printf "values: %s is missing" .component) }}
{{- $pods := $values.replicas }}
{{- if dig "autoscaling" "enabled" false $values }}
{{- $pods = $values.autoscaling.minReplicas }}
{{- end }}
{{- if gt (int $pods) 1 }}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ .component }}
  labels:
    {{- include "bernstein.labels" . | nindent 4 }}
spec:
  minAvailable: 1
  selector:
    matchLabels:
      {{- include "bernstein.selectorLabels" . | nindent 6 }}
{{- end }}
{{- end }}

{{/*
Pod spec field `topologySpreadConstraints` of a Deployment, as a list to put under
the key: spread the component's pods over the nodes, and over the availability zones
when the nodes have the zone label. ScheduleAnyway makes it a preference: pods stay
schedulable when there are more pods than nodes (autoscaler at its maximum on two
nodes), where a hard rule would leave them Pending.

  topologySpreadConstraints:
    {{- include "bernstein.topologySpread" (dict "context" $ "component" "poll") | trim | nindent 4 }}

`trim` removes the newline the list starts with.
*/}}
{{- define "bernstein.topologySpread" -}}
{{- range $key := list "kubernetes.io/hostname" "topology.kubernetes.io/zone" }}
- maxSkew: 1
  topologyKey: {{ $key }}
  whenUnsatisfiable: ScheduleAnyway
  labelSelector:
    matchLabels:
      {{- include "bernstein.selectorLabels" $ | nindent 6 }}
{{- end }}
{{- end }}

{{/*
Name of the Secret holding a component's password (postgres, redis):
<component>.existingSecret when set, else <component>-credentials, created by
the chart. Pods read its `password` key.
*/}}
{{- define "bernstein.secretName" -}}
{{- $values := index .context.Values .component | required (printf "values: %s is missing" .component) }}
{{- $values.existingSecret | default (printf "%s-credentials" .component) }}
{{- end }}

{{/*
Env entries to reach Redis (poll, worker): REDIS_HOST and REDIS_PASSWORD from the
Redis Secret. Items of a container's `env` list; pair it with the
`checksum/redis-secret` annotation. Needs no component, so it takes the root
context alone:

  {{- include "bernstein.env.redis" (dict "context" $) | nindent 12 }}
*/}}
{{- define "bernstein.env.redis" -}}
- name: REDIS_HOST
  value: redis
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "bernstein.secretName" (dict "context" .context "component" "redis") }}
      key: password
{{- end }}

{{/*
Env entries to reach PostgreSQL (worker, result): POSTGRES_HOST/PORT/DB/USER from
values and POSTGRES_PASSWORD from the PostgreSQL Secret. Same use as
bernstein.env.redis; pair it with the `checksum/postgres-secret` annotation.
*/}}
{{- define "bernstein.env.postgres" -}}
- name: POSTGRES_HOST
  value: postgres
- name: POSTGRES_PORT
  value: "5432"
- name: POSTGRES_DB
  value: {{ .context.Values.postgres.database | quote }}
- name: POSTGRES_USER
  value: {{ .context.Values.postgres.user | quote }}
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "bernstein.secretName" (dict "context" .context "component" "postgres") }}
      key: password
{{- end }}

{{/*
Checksum of a component's password, for a `checksum/<component>-secret`
annotation on the pod template of every workload reading it: a new password
changes the pod template, which rolls the pods.
- existingSecret: hash of that Secret's current data, read with lookup (empty
  with `helm template`, which has no cluster).
- password from values (postgres): hash of that value.
- generated password (redis): constant, as it never changes once created.
  Hashing the Secret instead would roll the pods on the first upgrade, because
  lookup finds nothing at install time.
*/}}
{{- define "bernstein.secretChecksum" -}}
{{- $values := index .context.Values .component | required (printf "values: %s is missing" .component) }}
{{- if $values.existingSecret }}
{{- (lookup "v1" "Secret" .context.Release.Namespace $values.existingSecret).data | default dict | toJson | sha256sum }}
{{- else }}
{{- $values.password | default "generated" | sha256sum }}
{{- end }}
{{- end }}
