# MCP Server Construction Prompt

## Overview

You are an AI agent tasked with constructing a **production-ready Kubernetes-Python MCP server** using the patterns established in this repository. The goal is to create an MCP server that enables AI agents to interact with a specific Kubernetes API or operator.

## Reference Implementation

The `example/cnpg-mcp/` directory contains a complete, production-ready MCP server for CloudNativePG that demonstrates all patterns you should follow. Study this implementation carefully.

## Required Features

### 1. Server Architecture (FastMCP)

**Framework**: Use FastMCP (>=2.0.0) with automatic schema generation.

**File Structure**:
```
src/
  {name}_mcp_server.py    # Main server entry point
  {name}_tools.py         # Tool implementations (shared between server modes)
  auth_fastmcp.py         # Auth0 OAuth proxy configuration
  user_hash.py            # User identification from JWT claims
```

**Server Entry Point Pattern** (`src/{name}_mcp_server.py`):
```python
from fastmcp import FastMCP, Context
import argparse

mcp = FastMCP("{server-name}")

# Import and register tools
from {name}_tools import tool1, tool2, ...

@mcp.tool(name="tool1")
async def tool1_wrapper(param1: str, ctx: Context = None):
    """Tool description."""
    return await tool1(ctx, param1=param1)

# Transport implementations
async def run_stdio_transport():
    await mcp.run_stdio_async()

def run_http_transport(host: str, port: int):
    from auth_fastmcp import create_auth0_oauth_proxy
    mcp.auth = create_auth0_oauth_proxy()
    app = mcp.http_app(transport="http", path="/mcp")
    # Add health check routes
    uvicorn.run(app, host=host, port=port)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if args.transport == "stdio":
        asyncio.run(run_stdio_transport())
    else:
        run_http_transport(args.host, args.port)
```

### 2. Tool Implementation Pattern

**Tools File** (`src/{name}_tools.py`):

```python
from typing import Optional, Literal
from pydantic import BaseModel, Field
from kubernetes import client, config
from fastmcp import Context as FastMCPContext
import asyncio

# Constants
CHARACTER_LIMIT = 25000

# Lazy Kubernetes client initialization
custom_api: Optional[client.CustomObjectsApi] = None
core_api: Optional[client.CoreV1Api] = None

def get_kubernetes_clients():
    """Lazy initialization of Kubernetes clients."""
    global custom_api, core_api
    if custom_api is None:
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        custom_api = client.CustomObjectsApi()
        core_api = client.CoreV1Api()
    return custom_api, core_api

# Pydantic models for input validation
class ToolInput(BaseModel):
    """Input for tool."""
    param1: str = Field(..., description="Description with examples")
    namespace: Optional[str] = Field(None, description="Kubernetes namespace")

# Tool implementations with comprehensive docstrings
async def my_tool(
    context: MCPContext,
    param1: str,
    namespace: Optional[str] = None,
    format: Literal["text", "json"] = "text"
) -> str:
    """
    Brief description.

    Detailed explanation of what this tool does and when to use it.

    Args:
        param1: Parameter description with usage guidance
        namespace: Kubernetes namespace (uses current context if not specified)
        format: Output format ('text' for human-readable, 'json' for structured)

    Returns:
        Description of return value format

    Examples:
        - my_tool(param1="value")
        - my_tool(param1="value", namespace="production")

    Error Handling:
        - 404: Resource not found → verify namespace and name
        - 403: Permission denied → check RBAC
    """
    try:
        if namespace is None:
            namespace = get_current_namespace()

        custom_api, _ = get_kubernetes_clients()
        result = await asyncio.to_thread(
            custom_api.list_namespaced_custom_object,
            group="...", version="...", namespace=namespace, plural="..."
        )

        return truncate_response(format_result(result, format))
    except Exception as e:
        return format_error_message(e, "context description")
```

### 3. Authentication (OIDC/OAuth2)

**Auth Module** (`src/auth_fastmcp.py`):

Features:
- FastMCP Auth0Provider for OAuth proxy
- YAML config file support (`/etc/mcp/oidc.yaml`)
- JWT signing key management (from file or environment)
- Redis client storage for session persistence
- Fernet encryption for stored OAuth tokens

Configuration sources (priority order):
1. Config file (`/etc/mcp/oidc.yaml`)
2. Environment variables (`OIDC_ISSUER`, `OIDC_AUDIENCE`, `AUTH0_CLIENT_ID`)

Required secrets:
- `client_secret_file`: Path to Auth0 client secret
- `jwt_signing_key_file`: Path to JWT signing key (256-bit hex)
- `storage_encryption_key_file`: Path to Fernet encryption key

### 4. User Identification

**User Hash Module** (`src/user_hash.py`):

- Extract `preferred_username` and `iss` from JWT claims
- Generate RFC 1123 DNS-compatible user IDs: `{sanitized-username}-{6-char-issuer-hash}`
- Support multiple claim names: `preferred_username`, `username`, `name`, `email`, `sub`

### 5. Helm Chart

**Chart Structure**:
```
chart/
  Chart.yaml              # App version, dependencies (redis)
  values.yaml             # Configuration values
  templates/
    deployment.yaml       # Main deployment with sidecars
    service.yaml          # ClusterIP service
    serviceaccount.yaml   # RBAC service account
    rolebinding.yaml      # Bind to operator roles
    configmap.yaml        # OIDC configuration
    ingress.yaml          # Optional ingress
    hpa.yaml              # Horizontal pod autoscaler
```

**Key Values** (`values.yaml`):
```yaml
replicaCount: 1
image:
  repository: your-registry/mcp-server
  tag: ""
serviceAccount:
  create: true
  name: "mcp-server"
service:
  type: ClusterIP
  port: 4204
oidc:
  issuer: "https://your-tenant.auth0.com"
  audience: "https://your-api/mcp"
redis:
  enabled: true
  architecture: standalone
jwt:
  secretName: ""  # Auto-generated from release name
```

**Deployment Pattern**:
- Mount OIDC config from ConfigMap at `/etc/mcp`
- Mount Auth0 credentials from Secret at `/etc/mcp/secrets/auth0`
- Mount JWT signing key from Secret at `/etc/mcp/secrets`
- Health probes: `/healthz` (liveness), `/readyz` (readiness)
- Optional test sidecar container

### 6. Dockerfile

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/*.py .

RUN useradd -m -u 1000 mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 4204

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:4204/healthz || exit 1

CMD ["python", "{name}_mcp_server.py", "--transport", "http", "--host", "0.0.0.0", "--port", "4204"]
```

### 7. Dependencies (`requirements.txt`)

```
# Core MCP
fastmcp>=2.0.0
py-key-value-aio[redis]

# Kubernetes
kubernetes>=28.0.0

# Validation
pydantic>=2.0.0
pyyaml>=6.0.0

# HTTP Transport
uvicorn[standard]>=0.27.0
starlette>=0.35.0
httpx>=0.25.0

# OIDC Authentication
authlib>=1.3.0
cryptography>=41.0.0

requests
python-dotenv
```

### 8. Test Infrastructure

**Test Runner** (`test/test-mcp.py`):
- Plugin-based test system with dependency ordering
- Support for stdio and HTTP transports
- Automatic token acquisition from Auth0
- JUnit XML output for CI/CD

**Test Plugin Pattern** (`test/plugins/test_{tool}.py`):
```python
from plugins import TestPlugin, TestResult, check_for_operational_error
import time

class MyToolTest(TestPlugin):
    tool_name = "my_tool"
    description = "Tests my_tool functionality"
    depends_on = []      # Hard dependencies
    run_after = []       # Soft ordering

    async def test(self, session) -> TestResult:
        start = time.time()
        try:
            result = await session.call_tool("my_tool", {"param1": "value"})
            response_text = result.content[0].text

            is_error, error_msg = check_for_operational_error(response_text)
            if is_error:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Tool returned operational error",
                    error=error_msg,
                    duration_ms=(time.time() - start) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message="Tool executed successfully",
                duration_ms=(time.time() - start) * 1000
            )
        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="Tool call failed",
                error=str(e),
                duration_ms=(time.time() - start) * 1000
            )
```

### 9. Utility Scripts (`bin/`)

- `create_secrets.py`: Generate Kubernetes secrets for Auth0 and JWT keys
- `setup_rbac.py`: Create ServiceAccount and RoleBindings
- `setup-auth0.py`: Configure Auth0 application and API

### 10. Makefile

```makefile
# Configuration
-include make.env
REGISTRY ?= your-registry
IMAGE_NAME ?= mcp-server
TAG ?= latest

# Targets
build:
	docker build -t $(REGISTRY)/$(IMAGE_NAME):$(TAG) .

push:
	docker push $(REGISTRY)/$(IMAGE_NAME):$(TAG)

helm-install:
	helm upgrade --install $(HELM_RELEASE) chart/ \
		--namespace $(HELM_NAMESPACE) \
		--set image.repository=$(REGISTRY)/$(IMAGE_NAME) \
		--set image.tag=$(TAG)

dev-start-http:
	./test/start-http.sh

dev-test-http:
	./test/test-mcp.py --transport http
```

## Design Principles

1. **Transport-agnostic core**: All tool logic works with any transport (stdio/HTTP)
2. **Lazy initialization**: Kubernetes clients initialized on first use
3. **Async operations**: Use `asyncio.to_thread()` for blocking Kubernetes calls
4. **Comprehensive docstrings**: FastMCP generates schemas from docstrings
5. **Actionable error messages**: Include HTTP status codes and resolution suggestions
6. **Response truncation**: Limit to 25,000 characters for LLM context
7. **RFC 1123 validation**: All Kubernetes resource names must be DNS-compatible
8. **Dry-run support**: Preview operations before execution
9. **Detail levels**: "concise" (default) and "detailed" output modes
10. **JSON format option**: Structured output for programmatic consumption

## Implementation Steps

1. **Define the target API/operator**:
   - Identify the Kubernetes CRD group, version, and plurals
   - List the operations needed (list, get, create, update, delete)
   - Determine required RBAC permissions

2. **Create tool implementations**:
   - Write Pydantic models for input validation
   - Implement async tool functions with comprehensive docstrings
   - Add error handling with actionable messages

3. **Set up authentication**:
   - Configure Auth0 or OIDC provider
   - Create auth_fastmcp.py with OAuth proxy
   - Set up JWT signing and Redis for session persistence

4. **Create Helm chart**:
   - Define values for OIDC, image, service
   - Create deployment with secret mounts
   - Add RBAC bindings to operator ClusterRoles

5. **Build test suite**:
   - Create test plugins for each tool
   - Define test dependencies for ordered execution
   - Add CI/CD integration with JUnit output

6. **Document**:
   - Create README with installation and usage
   - Document OIDC setup for target IdPs
   - Include troubleshooting guide

## Output

When complete, the MCP server should:
- Run locally with `python src/{name}_mcp_server.py`
- Deploy to Kubernetes with `helm install`
- Authenticate via Auth0/OIDC in HTTP mode
- Persist sessions in Redis
- Pass all automated tests
- Provide clear, actionable error messages

Use the `example/cnpg-mcp/` implementation as your reference for all patterns and conventions.
