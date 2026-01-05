# Deployment Pattern

This document describes the deployment pattern for production MCP servers.

## Overview

MCP servers are deployed to Kubernetes with:

1. **Container image** - Python application with FastMCP
2. **Helm chart** - Kubernetes manifests
3. **Redis sidecar** - OAuth session storage
4. **Ingress** - External access with TLS
5. **RBAC** - Kubernetes permissions

## Container Image

### Dockerfile Pattern

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy requirements first (for layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:4207/health || exit 1

# Expose port
EXPOSE 4207

# Run server
CMD ["python", "src/server.py", "--transport", "http", "--port", "4207"]
```

### Multi-stage Build (for smaller images)

```dockerfile
# Build stage
FROM python:3.11-slim as builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/build/deps -r requirements.txt

# Runtime stage
FROM python:3.11-slim

RUN useradd --create-home appuser
WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /build/deps /usr/local/lib/python3.11/site-packages/

# Copy application
COPY src/ ./src/

USER appuser
EXPOSE 4207
CMD ["python", "src/server.py", "--transport", "http", "--port", "4207"]
```

## Build Automation (Makefile)

```makefile
# Configuration
REGISTRY ?= your-registry.example.com
IMAGE_NAME ?= mcp-server
TAG ?= latest
PLATFORM ?= linux/amd64
CONTAINER_TOOL ?= docker
HELM_RELEASE ?= mcp-server
HELM_NAMESPACE ?= mcp

IMAGE_FULL := $(REGISTRY)/$(IMAGE_NAME):$(TAG)

# Build targets
.PHONY: build
build:
	$(CONTAINER_TOOL) build --tag $(IMAGE_FULL) --platform $(PLATFORM) .

.PHONY: push
push:
	$(CONTAINER_TOOL) push $(IMAGE_FULL)

.PHONY: build-push
build-push: build push

# Helm targets
.PHONY: helm-deps
helm-deps:
	helm dependency update chart/

.PHONY: helm-lint
helm-lint:
	helm lint chart/

.PHONY: helm-install
helm-install:
	helm upgrade --install $(HELM_RELEASE) chart/ \
		--namespace $(HELM_NAMESPACE) \
		--create-namespace \
		--set image.repository=$(REGISTRY)/$(IMAGE_NAME) \
		--set image.tag=$(TAG) \
		--wait

.PHONY: helm-uninstall
helm-uninstall:
	helm uninstall $(HELM_RELEASE) --namespace $(HELM_NAMESPACE)
```

## Pre-deployment Setup

### 1. Generate Configuration Files

```bash
# Run the configuration generator (included in scaffold)
python bin/make-config.py

# This creates:
# - auth0-config.json (Auth0 credentials)
# - helm-values.yaml (Helm deployment values)
# - .env (local development environment)
# - gitignore-additions.txt (entries to add to .gitignore)
```

### 2. Build and Push Container Image

```bash
# Build the container image
make build

# Push to registry
make push
```

### 3. Create Kubernetes Secrets

```bash
# Install mcp-base CLI
pip install mcp-base

# Setup Auth0 resources (optional - if configuring Auth0 automatically)
mcp-base setup-oidc --auth0 --token $AUTH0_MGMT_TOKEN

# Create Kubernetes secrets from auth0-config.json
mcp-base create-secrets \
    --namespace mcp \
    --release-name mcp-server
```

### 4. Setup RBAC (if needed)

```bash
# Create RBAC resources
mcp-base setup-rbac \
    --namespace mcp \
    --service-account mcp-server \
    --scope cluster
```

### 5. Update Helm Dependencies

```bash
helm dependency update chart/
```

## Deployment Commands

### Basic Installation

```bash
helm upgrade --install mcp-server chart/ \
    --namespace mcp \
    --create-namespace \
    --set image.repository=registry.example.com/mcp-server \
    --set image.tag=v1.0.0 \
    --set oidc.issuer=https://tenant.auth0.com/ \
    --set oidc.audience=mcp-api
```

### With Custom Values File

```yaml
# values-production.yaml
image:
  repository: registry.example.com/mcp-server
  tag: v1.0.0

oidc:
  issuer: https://tenant.auth0.com/
  audience: mcp-api

ingress:
  enabled: true
  className: nginx
  host: mcp.example.com
  tls:
    enabled: true
    secretName: mcp-tls

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 200m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

```bash
helm upgrade --install mcp-server chart/ \
    --namespace mcp \
    --values values-production.yaml
```

## Ingress Configuration

### With nginx-ingress and cert-manager

```yaml
# values for ingress
ingress:
  enabled: true
  className: nginx
  host: mcp.example.com
  path: /
  pathType: Prefix
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
  tls:
    enabled: true
    secretName: mcp-tls
```

### Manual TLS Secret

```bash
kubectl create secret tls mcp-tls \
    --namespace mcp \
    --cert=path/to/tls.crt \
    --key=path/to/tls.key
```

## Monitoring and Observability

### Health Endpoints

The server exposes:
- `/health` - Kubernetes health check (unauthenticated)
- `/mcp` - MCP protocol endpoint (authenticated)

### Prometheus Metrics (optional)

```yaml
# In deployment
spec:
  template:
    metadata:
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "4207"
        prometheus.io/path: "/metrics"
```

### Logging

```yaml
# In deployment
env:
  - name: LOG_LEVEL
    value: "INFO"
  - name: LOG_FORMAT
    value: "json"
```

## Operational Commands

### Check Status

```bash
# Helm release status
helm status mcp-server --namespace mcp

# Pod status
kubectl get pods -n mcp -l app.kubernetes.io/name=mcp-server

# Logs
kubectl logs -n mcp -l app.kubernetes.io/name=mcp-server --tail=100 -f
```

### Port Forward for Local Testing

```bash
kubectl port-forward -n mcp svc/mcp-server 4207:4207
```

### Scale Manually

```bash
kubectl scale deployment -n mcp mcp-server --replicas=3
```

### Rolling Update

```bash
# Update image tag
helm upgrade mcp-server chart/ \
    --namespace mcp \
    --reuse-values \
    --set image.tag=v1.1.0
```

### Rollback

```bash
# List history
helm history mcp-server --namespace mcp

# Rollback to previous
helm rollback mcp-server --namespace mcp

# Rollback to specific revision
helm rollback mcp-server 3 --namespace mcp
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy MCP Server

on:
  push:
    tags: ['v*']

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Login to Registry
        run: echo ${{ secrets.REGISTRY_PASSWORD }} | docker login -u ${{ secrets.REGISTRY_USERNAME }} --password-stdin ${{ secrets.REGISTRY }}

      - name: Build and Push
        run: |
          TAG=${GITHUB_REF#refs/tags/}
          docker build -t ${{ secrets.REGISTRY }}/mcp-server:$TAG .
          docker push ${{ secrets.REGISTRY }}/mcp-server:$TAG

      - name: Deploy to Kubernetes
        run: |
          TAG=${GITHUB_REF#refs/tags/}
          helm upgrade --install mcp-server chart/ \
            --namespace mcp \
            --set image.tag=$TAG \
            --wait
```

## Best Practices

1. **Use non-root user** - Security best practice
2. **Include health checks** - For Kubernetes probes
3. **Set resource limits** - Prevent resource exhaustion
4. **Enable autoscaling** - Handle variable load
5. **Use rolling updates** - Zero-downtime deployments
6. **Store secrets securely** - Kubernetes secrets or external vault
7. **Enable TLS** - Always use HTTPS in production
8. **Monitor logs and metrics** - Observability is critical
9. **Test in staging first** - Before production deployment
10. **Use GitOps** - Version control for deployments
