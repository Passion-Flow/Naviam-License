{{/*
Expand the name of the chart.
*/}}
{{- define "forge.name" -}}
{{- default .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "forge.fullname" -}}
{{- $name := default .Chart.Name }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "forge.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "forge.labels" -}}
helm.sh/chart: {{ include "forge.chart" . }}
{{ include "forge.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels (must be stable across upgrades — no helm/version labels here)
*/}}
{{- define "forge.selectorLabels" -}}
app.kubernetes.io/name: {{ include "forge.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* labels defined by user */}}
{{- define "forge.ud.labels" -}}
{{- if .Values.labels }}
{{- toYaml .Values.labels }}
{{- end -}}
{{- end -}}

{{/* annotations defined by user */}}
{{- define "forge.ud.annotations" -}}
{{- if .Values.annotations }}
{{- toYaml .Values.annotations }}
{{- end -}}
{{- end -}}

{{/* Extra labels on all workload pod templates (see global.podLabels). Not added to selectors. */}}
{{- define "forge.podExtraLabels" -}}
{{- if .Values.global.podLabels }}
{{- toYaml .Values.global.podLabels }}
{{- end }}
{{- end }}

{{/* Pod security context — applied to all Forge Pods */}}
{{- define "forge.podSecurityContext" -}}
{{- if .Values.global.podSecurityContext }}
{{- toYaml .Values.global.podSecurityContext }}
{{- end }}
{{- end }}

{{/* Container security context — applied to all Forge containers */}}
{{- define "forge.containerSecurityContext" -}}
{{- if .Values.global.containerSecurityContext }}
{{- toYaml .Values.global.containerSecurityContext }}
{{- end }}
{{- end }}

{{/* Per-component fullname: forge-<role> */}}
{{- define "forge.componentName" -}}
{{- printf "%s-%s" (include "forge.fullname" .root) .component | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Image reference: <registry>/<repository>:<tag>, with tag falling back to .Chart.AppVersion.
     `image:` block now lives inside each component (api / worker / scheduler / web). */}}
{{- define "forge.image" -}}
{{- $img := (index .root.Values .component).image -}}
{{- $tag := $img.tag | default .root.Chart.AppVersion -}}
{{- if .root.Values.imageRegistry -}}
{{ .root.Values.imageRegistry }}/{{ $img.repository }}:{{ $tag }}
{{- else -}}
{{ $img.repository }}:{{ $tag }}
{{- end -}}
{{- end -}}

{{/*
Name of the auto-generated Secret (only consumed when the corresponding
externalSecretName / *ExistingSecret is empty).
*/}}
{{- define "forge.secretName" -}}
{{- printf "%s-secret" (include "forge.fullname" .) -}}
{{- end -}}

{{/* Effective Secret name for each subsystem */}}
{{- define "forge.database.secretName" -}}
{{- if .Values.database.externalSecretName -}}
{{ .Values.database.externalSecretName }}
{{- else -}}
{{ include "forge.secretName" . }}
{{- end -}}
{{- end -}}

{{- define "forge.cache.secretName" -}}
{{- if .Values.cache.externalSecretName -}}
{{ .Values.cache.externalSecretName }}
{{- else -}}
{{ include "forge.secretName" . }}
{{- end -}}
{{- end -}}

{{- define "forge.objectStorage.secretName" -}}
{{- if .Values.objectStorage.externalSecretName -}}
{{ .Values.objectStorage.externalSecretName }}
{{- else -}}
{{ include "forge.secretName" . }}
{{- end -}}
{{- end -}}

{{- define "forge.signing.secretName" -}}
{{- if .Values.signing.masterPassphraseExistingSecret -}}
{{ .Values.signing.masterPassphraseExistingSecret }}
{{- else -}}
{{ include "forge.secretName" . }}
{{- end -}}
{{- end -}}

{{- define "forge.auth.secretName" -}}
{{- if .Values.auth.sessionSecretExistingSecret -}}
{{ .Values.auth.sessionSecretExistingSecret }}
{{- else -}}
{{ include "forge.secretName" . }}
{{- end -}}
{{- end -}}

{{/*
Object Storage provider-specific access key & secret keys (used by the
generated Secret). Returns a string "<accessKey>|<secretKey>" — the
caller splits with `split` to keep the helper count low.
*/}}
{{- define "forge.objectStorage.credentials" -}}
{{- $os := .Values.objectStorage -}}
{{- if eq $os.type "s3" -}}
{{ $os.s3.accessKey }}|{{ $os.s3.secretKey }}
{{- else if eq $os.type "azure-blob" -}}
{{ $os.azureBlob.accountName }}|{{ $os.azureBlob.accountKey }}
{{- else if eq $os.type "aliyun-oss" -}}
{{ $os.aliyunOss.accessKey }}|{{ $os.aliyunOss.secretKey }}
{{- else if eq $os.type "google-storage" -}}
|{{ $os.googleStorage.serviceAccountJson }}
{{- else if eq $os.type "tencent-cos" -}}
{{ $os.tencentCos.secretId }}|{{ $os.tencentCos.secretKey }}
{{- else if eq $os.type "volcengine-tos" -}}
{{ $os.volcengineTos.accessKey }}|{{ $os.volcengineTos.secretKey }}
{{- else if eq $os.type "huawei-obs" -}}
{{ $os.huaweiObs.accessKey }}|{{ $os.huaweiObs.secretKey }}
{{- else if and (eq $os.type "local") (eq $os.local.mode "minio") -}}
{{ $os.local.minio.accessKey }}|{{ $os.local.minio.secretKey }}
{{- else -}}
|
{{- end -}}
{{- end -}}

{{/*
Object Storage endpoint resolution by provider.
*/}}
{{- define "forge.objectStorage.endpoint" -}}
{{- $os := .Values.objectStorage -}}
{{- if eq $os.type "s3" -}}
{{ $os.s3.endpoint }}
{{- else if eq $os.type "azure-blob" -}}
{{ $os.azureBlob.accountUrl }}
{{- else if eq $os.type "aliyun-oss" -}}
{{ $os.aliyunOss.endpoint }}
{{- else if eq $os.type "tencent-cos" -}}
{{ $os.tencentCos.scheme }}://cos.{{ $os.tencentCos.region }}.myqcloud.com
{{- else if eq $os.type "volcengine-tos" -}}
{{ $os.volcengineTos.endpoint }}
{{- else if eq $os.type "huawei-obs" -}}
{{ $os.huaweiObs.server }}
{{- else if and (eq $os.type "local") (eq $os.local.mode "minio") -}}
{{ $os.local.minio.endpoint }}
{{- else -}}
{{ "" }}
{{- end -}}
{{- end -}}

{{/*
Object Storage region resolution by provider.
*/}}
{{- define "forge.objectStorage.region" -}}
{{- $os := .Values.objectStorage -}}
{{- if eq $os.type "s3" -}}
{{ $os.s3.region }}
{{- else if eq $os.type "aliyun-oss" -}}
{{ $os.aliyunOss.region }}
{{- else if eq $os.type "tencent-cos" -}}
{{ $os.tencentCos.region }}
{{- else if eq $os.type "volcengine-tos" -}}
{{ $os.volcengineTos.region }}
{{- else -}}
{{ "" }}
{{- end -}}
{{- end -}}

{{/*
Shared application env block — wired into all 3 backend Deployments
(api / worker / scheduler). Field names match ../docker/.env.example.
*/}}
{{- define "forge.appEnv" -}}
# ─── Database
- name: DATABASE_TYPE
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: DATABASE_TYPE } }
- name: DATABASE_HOST
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: DATABASE_HOST } }
- name: DATABASE_PORT
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: DATABASE_PORT } }
- name: DATABASE_USERNAME
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: DATABASE_USERNAME } }
- name: DATABASE_DATABASE
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: DATABASE_DATABASE } }
- name: DATABASE_POOL_SIZE
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: DATABASE_POOL_SIZE } }
- name: DATABASE_SSL_MODE
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: DATABASE_SSL_MODE } }
- name: DATABASE_PASSWORD
  valueFrom: { secretKeyRef: { name: {{ include "forge.database.secretName" . }}, key: DATABASE_PASSWORD } }
# ─── Cache
- name: CACHE_TYPE
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: CACHE_TYPE } }
- name: CACHE_HOST
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: CACHE_HOST } }
- name: CACHE_PORT
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: CACHE_PORT } }
- name: CACHE_USERNAME
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: CACHE_USERNAME } }
- name: CACHE_PASSWORD
  valueFrom: { secretKeyRef: { name: {{ include "forge.cache.secretName" . }}, key: CACHE_PASSWORD } }
- name: CACHE_DB_APP
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: CACHE_DB_APP } }
- name: CACHE_DB_SESSION
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: CACHE_DB_SESSION } }
- name: CACHE_DB_CELERY_BROKER
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: CACHE_DB_CELERY_BROKER } }
- name: CACHE_DB_CELERY_RESULT
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: CACHE_DB_CELERY_RESULT } }
# ─── Object Storage
- name: OBJECT_STORAGE_TYPE
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: OBJECT_STORAGE_TYPE } }
- name: OBJECT_STORAGE_ENDPOINT
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: OBJECT_STORAGE_ENDPOINT } }
- name: OBJECT_STORAGE_REGION
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: OBJECT_STORAGE_REGION } }
- name: OBJECT_STORAGE_BUCKET_LICENSE_FILES
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: OBJECT_STORAGE_BUCKET_LICENSE_FILES } }
- name: OBJECT_STORAGE_BUCKET_PUBLIC_KEYS
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: OBJECT_STORAGE_BUCKET_PUBLIC_KEYS } }
- name: OBJECT_STORAGE_BUCKET_AUDIT
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: OBJECT_STORAGE_BUCKET_AUDIT } }
- name: OBJECT_STORAGE_ACCESS_KEY_ID
  valueFrom:
    secretKeyRef:
      name: {{ include "forge.objectStorage.secretName" . }}
      key: OBJECT_STORAGE_ACCESS_KEY_ID
      optional: true
- name: OBJECT_STORAGE_ACCESS_KEY_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "forge.objectStorage.secretName" . }}
      key: OBJECT_STORAGE_ACCESS_KEY_SECRET
      optional: true
# ─── Signing / Key Storage
- name: SIGNING_DEFAULT_ALGORITHM
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: SIGNING_DEFAULT_ALGORITHM } }
- name: KEY_STORAGE_BACKEND
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: KEY_STORAGE_BACKEND } }
- name: KEY_STORAGE_LOCAL_PATH
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: KEY_STORAGE_LOCAL_PATH } }
- name: KEY_MASTER_PASSPHRASE
  valueFrom: { secretKeyRef: { name: {{ include "forge.signing.secretName" . }}, key: KEY_MASTER_PASSPHRASE } }
# ─── Auth
- name: AUTH_SESSION_SECRET
  valueFrom: { secretKeyRef: { name: {{ include "forge.auth.secretName" . }}, key: AUTH_SESSION_SECRET } }
- name: AUTH_SESSION_MAX_AGE_SECONDS
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: AUTH_SESSION_MAX_AGE_SECONDS } }
# ─── Heartbeat
- name: HEARTBEAT_WINDOW_SECONDS
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: HEARTBEAT_WINDOW_SECONDS } }
- name: HEARTBEAT_THRESHOLD
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: HEARTBEAT_THRESHOLD } }
- name: HEARTBEAT_GRACE_COUNT
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: HEARTBEAT_GRACE_COUNT } }
# ─── Logging
- name: LOG_LEVEL
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: LOG_LEVEL } }
- name: LOG_FORMAT
  valueFrom: { configMapKeyRef: { name: {{ include "forge.fullname" . }}-config, key: LOG_FORMAT } }
{{- end -}}
