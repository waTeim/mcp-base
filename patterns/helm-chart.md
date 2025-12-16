# Helm Chart Pattern

This document describes the pattern for creating Helm charts for MCP servers.

## Overview

MCP server Helm charts are created by modifying the output of `helm create` and adding:

1. **Redis dependency** - For OAuth session storage
2. **OIDC ConfigMap** - Authentication configuration
3. **Auth0 secrets** - Credential management
4. **RBAC resources** - Kubernetes permissions

## Chart Structure

```
chart/
├── Chart.yaml          # Chart metadata with dependencies
├── values.yaml         # Default configuration values
├── templates/
│   ├── _helpers.tpl    # Template helper functions
│   ├── deployment.yaml # Main deployment
│   ├── service.yaml    # Service exposure
│   ├── configmap.yaml  # OIDC configuration
│   ├── serviceaccount.yaml
│   ├── rolebinding.yaml
│   ├── ingress.yaml    # Optional ingress
│   └── hpa.yaml        # Optional autoscaling
└── charts/             # Dependency charts (Redis)
```

## Chart.yaml with Redis Dependency

```yaml
apiVersion: v2
name: my-mcp-server
description: MCP server for managing resources
type: application
version: 0.1.0
appVersion: "1.0.0"

dependencies:
  - name: redis
    version: "0.16.4"
    repository: "oci://registry-1.docker.io/cloudpirates"
    condition: redis.enabled
    tags:
      - persistence
```

## Key values.yaml Sections

### Image Configuration

```yaml
image:
  repository: your-registry.example.com/mcp-server
  pullPolicy: IfNotPresent
  tag: ""  # Defaults to chart appVersion

imagePullSecrets: []
```

### OIDC Configuration

```yaml
oidc:
  issuer: "https://tenant.auth0.com/"
  audience: "mcp-api"
  jwksUri: ""  # Auto-discovered from issuer if empty
  scope: "openid profile email"
```

### Redis Configuration

```yaml
redis:
  enabled: true
  architecture: standalone
  auth:
    enabled: false
  master:
    persistence:
      enabled: false
```

### Auth0 Secrets Reference

```yaml
auth0:
  existingSecret: ""  # Name of existing secret
  # If existingSecret is empty, these are used:
  domain: ""
  clientId: ""
  clientSecret: ""
```

### Service Configuration

```yaml
service:
  type: ClusterIP
  port: 4207

ingress:
  enabled: false
  className: ""
  host: mcp.example.com
  path: /
  pathType: Prefix
  tls:
    enabled: false
    secretName: ""
```

### Resource Limits

```yaml
resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

### RBAC Configuration

```yaml
serviceAccount:
  create: true
  name: ""
  annotations: {}

# ClusterRoles to bind (from operators)
operatorClusterRoles: []
  # - cnpg-cloudnative-pg-edit
  # - strimzi-kafka-edit
```

## Deployment Template Pattern

Key sections of deployment.yaml:

### Environment Variables from Secrets

```yaml
env:
  - name: AUTH0_DOMAIN
    valueFrom:
      secretKeyRef:
        name: {{ .Values.auth0.existingSecret | default (printf "%s-auth0-credentials" .Release.Name) }}
        key: auth0-domain
  - name: AUTH0_CLIENT_ID
    valueFrom:
      secretKeyRef:
        name: {{ .Values.auth0.existingSecret | default (printf "%s-auth0-credentials" .Release.Name) }}
        key: server-client-id
  - name: AUTH0_CLIENT_SECRET
    valueFrom:
      secretKeyRef:
        name: {{ .Values.auth0.existingSecret | default (printf "%s-auth0-credentials" .Release.Name) }}
        key: server-client-secret
```

### Environment Variables from ConfigMap

```yaml
env:
  - name: OIDC_ISSUER
    valueFrom:
      configMapKeyRef:
        name: {{ include "chart.fullname" . }}-oidc-config
        key: issuer
  - name: OIDC_AUDIENCE
    valueFrom:
      configMapKeyRef:
        name: {{ include "chart.fullname" . }}-oidc-config
        key: audience
```

### Redis Connection

```yaml
{{- if .Values.redis.enabled }}
- name: REDIS_URL
  value: "redis://{{ .Release.Name }}-redis-master:6379"
{{- end }}
```

### Health Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 5
  periodSeconds: 10
```

## ConfigMap for OIDC

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "chart.fullname" . }}-oidc-config
data:
  issuer: {{ .Values.oidc.issuer | quote }}
  audience: {{ .Values.oidc.audience | quote }}
  jwks-uri: {{ .Values.oidc.jwksUri | default "" | quote }}
  scope: {{ .Values.oidc.scope | quote }}
```

## RoleBinding for Operator ClusterRoles

```yaml
# Always create secrets Role for credential management
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: {{ include "chart.fullname" . }}-secrets
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: {{ include "chart.fullname" . }}-secrets
subjects:
  - kind: ServiceAccount
    name: {{ include "chart.serviceAccountName" . }}
roleRef:
  kind: Role
  name: {{ include "chart.fullname" . }}-secrets
  apiGroup: rbac.authorization.k8s.io
---
# Bind to operator-provided ClusterRoles
{{- range .Values.operatorClusterRoles }}
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: {{ include "chart.fullname" $ }}-{{ . | replace "." "-" }}
subjects:
  - kind: ServiceAccount
    name: {{ include "chart.serviceAccountName" $ }}
    namespace: {{ $.Release.Namespace }}
roleRef:
  kind: ClusterRole
  name: {{ . }}
  apiGroup: rbac.authorization.k8s.io
---
{{- end }}
```

## Helper Functions (_helpers.tpl)

```yaml
{{- define "chart.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "chart.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "chart.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "chart.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "chart.labels" -}}
helm.sh/chart: {{ include "chart.chart" . }}
{{ include "chart.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "chart.selectorLabels" -}}
app.kubernetes.io/name: {{ include "chart.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

## Installation Commands

```bash
# Update dependencies (downloads Redis chart)
helm dependency update chart/

# Lint chart
helm lint chart/

# Template locally (debug)
helm template my-release chart/ \
  --namespace mcp \
  --set image.tag=v1.0.0

# Install
helm upgrade --install my-release chart/ \
  --namespace mcp \
  --create-namespace \
  --set image.repository=registry.example.com/mcp-server \
  --set image.tag=v1.0.0 \
  --set oidc.issuer=https://tenant.auth0.com/ \
  --set oidc.audience=mcp-api

# With existing secrets
helm upgrade --install my-release chart/ \
  --namespace mcp \
  --set auth0.existingSecret=my-auth0-secret
```

## Best Practices

1. **Use `helm create` as base** - Then modify for MCP requirements
2. **Always include Redis** - Required for OAuth session storage
3. **Separate secrets from config** - ConfigMap for non-sensitive, Secret for credentials
4. **Use operator ClusterRoles** - Don't duplicate RBAC rules
5. **Include health endpoints** - For Kubernetes probes
6. **Support existing secrets** - Allow pre-created credentials
7. **Document values.yaml** - Add comments for all options
