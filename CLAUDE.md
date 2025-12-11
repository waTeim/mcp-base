# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mcp-base** is an MCP server that assists AI agents in constructing production-ready, Kubernetes-Python-centric remote MCP servers. It provides resources, prompts, and tools to scaffold and generate MCP servers following established patterns.

**Key components**:
- `prompts/`: Construction prompts for guiding MCP server generation
- `example/cnpg-mcp/`: Complete reference implementation (CloudNativePG MCP server)

## Reference Implementation Features

The `example/cnpg-mcp/` directory demonstrates all patterns that mcp-base helps construct:

### Server Architecture
- **FastMCP** framework with automatic schema generation from docstrings
- **Transport-agnostic design**: stdio (Claude Desktop) and HTTP/SSE (production)
- **Async operations**: All I/O via `asyncio.to_thread()`
- **Lazy Kubernetes client initialization**

### Authentication (OIDC/OAuth2)
- **FastMCP Auth0Provider** for OAuth proxy token issuance
- **YAML config file** support (`/etc/mcp/oidc.yaml`)
- **JWT signing key** management (file or environment variable)
- **Redis session persistence** with Fernet encryption
- **User identification** from JWT claims (RFC 1123 compatible IDs)

### Kubernetes Integration
- **kubernetes-python client** with CRD support
- **RBAC** using operator-provided ClusterRoles
- **Secret management** for credentials and passwords
- **Namespace inference** from kubeconfig context

### Deployment
- **Helm chart** with Redis dependency
- **ConfigMap** for OIDC configuration
- **Secrets** for Auth0 credentials and JWT signing key
- **Health probes**: `/healthz`, `/readyz`
- **Optional test sidecar** for dual authentication modes

### Testing
- **Plugin-based test system** with dependency ordering
- **Topological sort** for test execution order
- **JUnit XML output** for CI/CD integration
- **Auth proxy** for simplified HTTP testing

## Development Environment

### Devcontainer
- Python 3.12, Go 1.24, Node.js LTS
- kubectl (v1.30), helm, kubelogin
- Claude Code CLI, MCP Inspector

### Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run example server (stdio)
python example/cnpg-mcp/src/cnpg_mcp_server.py

# Run example server (HTTP with OIDC)
export OIDC_ISSUER=https://your-tenant.auth0.com
export OIDC_AUDIENCE=https://your-api/mcp
python example/cnpg-mcp/src/cnpg_mcp_server.py --transport http --port 3000

# Run tests
python example/cnpg-mcp/test/test-mcp.py

# Build container
cd example/cnpg-mcp && make build

# Deploy via Helm
cd example/cnpg-mcp && make helm-install
```

## Key Patterns to Extract

### Tool Implementation Pattern
```python
@mcp.tool(name="tool_name")
async def tool_wrapper(param1: str, ctx: Context = None):
    """Brief description."""
    return await tool_impl(ctx, param1=param1)

async def tool_impl(context: MCPContext, param1: str, ...) -> str:
    """
    Brief description.

    Args:
        param1: Description with examples

    Returns:
        Description of format

    Examples:
        - tool_impl(param1="value")

    Error Handling:
        - 404: Resource not found
        - 403: Permission denied
    """
    try:
        # Async Kubernetes call
        result = await asyncio.to_thread(api.method, ...)
        return truncate_response(format_result(result))
    except Exception as e:
        return format_error_message(e, "context")
```

### Configuration Priority
1. Config file (`/etc/mcp/oidc.yaml`)
2. Environment variables
3. Defaults

### Secret Mounting Pattern
- Auth0 credentials: `/etc/mcp/secrets/auth0/`
- JWT signing key: `/etc/mcp/secrets/jwt-signing-key`
- Storage encryption key: `/etc/mcp/secrets/storage-encryption-key`

## File Organization

### Core Prompt
- `prompts/construct-mcp-server.md`: Comprehensive guide for building MCP servers

### Reference Implementation (`example/cnpg-mcp/`)
```
src/
  cnpg_mcp_server.py     # Main entry point
  cnpg_tools.py          # Tool implementations
  auth_fastmcp.py        # Auth0 OAuth proxy
  user_hash.py           # User identification
test/
  test-mcp.py            # Test runner
  plugins/               # Test plugins
bin/
  create_secrets.py      # K8s secret generator
  setup_rbac.py          # RBAC setup
chart/
  Chart.yaml             # Helm chart
  values.yaml            # Configuration
  templates/             # K8s manifests
```

## Construction Workflow

When using mcp-base to construct a new MCP server:

1. **Define target API**: Identify CRD group/version/plural, operations, RBAC needs
2. **Use construction prompt**: `prompts/construct-mcp-server.md`
3. **Follow reference patterns**: Copy and adapt from `example/cnpg-mcp/`
4. **Implement tools**: Start with list/get, then create/update/delete
5. **Set up authentication**: Configure Auth0 or OIDC provider
6. **Create Helm chart**: Adapt from reference chart
7. **Write tests**: Create plugins for each tool
8. **Document**: README, OIDC setup, troubleshooting

## Resources

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
- [CloudNativePG Documentation](https://cloudnative-pg.io/documentation/current/)
