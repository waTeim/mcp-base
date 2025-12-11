# Build MCP-Base

## Objective

Build **mcp-base**, an MCP server that helps AI agents construct production-ready, Kubernetes-Python remote MCP servers. It exposes embedded templates, patterns, and tools via HTTP (Streamable HTTP transport only).

## Constraints

- **HTTP only** - No stdio transport. Uses FastMCP with Streamable HTTP.
- **Self-contained** - All resources embedded in `templates/` and `patterns/` directories
- **example/ is source only** - Used for extraction, will not exist at runtime

---

## Target Directory Structure

```
mcp-base/
├── src/
│   ├── mcp_base_server.py      # Main MCP server (FastMCP, HTTP)
│   ├── resources.py            # Resource handlers for templates/patterns
│   └── tools.py                # Scaffolding and generation tools
│
├── templates/                   # Extracted from example/, embedded
│   ├── server/
│   │   ├── entry_point.py.j2   # Parameterized server entry point
│   │   ├── tools.py.j2         # Tool implementations with imports
│   │   ├── mcp_context.py      # MCPContext class + with_mcp_context decorator (as-is)
│   │   ├── auth_oidc.py        # Generic OIDC auth (as-is)
│   │   ├── auth_fastmcp.py.j2  # FastMCP Auth0 provider
│   │   └── user_hash.py        # User ID from JWT (as-is)
│   │
│   ├── container/
│   │   ├── Dockerfile.j2
│   │   └── requirements.txt
│   │
│   ├── helm/
│   │   ├── Chart.yaml.j2
│   │   ├── values.yaml.j2
│   │   └── templates/
│   │       ├── _helpers.tpl.j2
│   │       ├── deployment.yaml.j2
│   │       ├── service.yaml.j2
│   │       ├── serviceaccount.yaml.j2
│   │       ├── configmap.yaml.j2
│   │       ├── ingress.yaml.j2
│   │       ├── hpa.yaml.j2
│   │       └── rolebinding.yaml.j2
│   │
│   ├── test/
│   │   ├── test_runner.py.j2
│   │   ├── plugin_base.py      # TestPlugin, TestResult (as-is)
│   │   ├── get_user_token.py   # (as-is)
│   │   └── auth_proxy.py       # (as-is)
│   │
│   ├── bin/
│   │   ├── create_secrets.py.j2
│   │   ├── setup_auth0.py      # (as-is)
│   │   └── setup_rbac.py.j2
│   │
│   └── Makefile.j2
│
├── patterns/                    # Documentation with code examples
│   ├── tool_implementation.md
│   ├── kubernetes_client.md
│   ├── secret_management.md
│   ├── test_plugin.md
│   └── helm_rbac.md
│
├── requirements.txt             # mcp-base dependencies
├── Dockerfile                   # mcp-base container
└── CLAUDE.md
```

---

## Phase 1: Extract Templates

Extract generic files from `example/cnpg-mcp/` into `templates/`.

### Files to Copy As-Is (Fully Generic)

| Source | Destination |
|--------|-------------|
| `example/cnpg-mcp/src/auth_oidc.py` | `templates/server/auth_oidc.py` |
| `example/cnpg-mcp/src/user_hash.py` | `templates/server/user_hash.py` |
| `example/cnpg-mcp/src/cnpg_tools.py` (lines 45-165) | `templates/server/mcp_context.py` |
| `example/cnpg-mcp/requirements.txt` | `templates/container/requirements.txt` |
| `example/cnpg-mcp/test/plugins/__init__.py` | `templates/test/plugin_base.py` |
| `example/cnpg-mcp/test/get-user-token.py` | `templates/test/get_user_token.py` |
| `example/cnpg-mcp/test/mcp-auth-proxy.py` | `templates/test/auth_proxy.py` |
| `example/cnpg-mcp/bin/setup-auth0.py` | `templates/bin/setup_auth0.py` |

### Files to Parameterize (Convert to Jinja2)

Create `.j2` templates with these substitutions:

**`templates/server/entry_point.py.j2`** (from `cnpg_mcp_server.py`):
- Replace `"cloudnative-pg"` → `"{{ server_name }}"`
- Replace tool imports → `{% for tool in tools %}...{% endfor %}`
- Replace tool registrations → loop over tools
- Remove stdio transport code (HTTP only)

**`templates/server/auth_fastmcp.py.j2`** (from `auth_fastmcp.py`):
- Replace `"CloudNativePG"` in logs → `"{{ server_name }}"`

**`templates/container/Dockerfile.j2`** (from `Dockerfile`):
- Replace `cnpg_mcp_server.py` → `{{ server_name_snake }}_server.py`
- Replace port `4204` → `{{ port }}`

**`templates/helm/*.j2`** (from `chart/`):
- Replace `cnpg-mcp` → `{{ chart_name }}`
- Replace CNPG-specific ClusterRole names → `{{ operator_cluster_roles }}`

> **Helm Chart Origin**: The example chart was created via `helm create cnpg-mcp` and then modified. Generated charts should follow the same pattern.

> **Redis Dependency**: The chart MUST include a Redis dependency for OAuth client session storage. See `Chart.yaml`:
> ```yaml
> dependencies:
>   - name: redis
>     version: "0.16.4"
>     repository: "oci://registry-1.docker.io/cloudpirates"
>     condition: redis.enabled
> ```

**`templates/bin/setup_rbac.py.j2`** (from `bin/setup_rbac.py`):
- Replace `"postgresql.cnpg.io"` → `"{{ k8s_api_group }}"`
- Replace resource lists → `{{ k8s_resources }}`

**`templates/test/test_runner.py.j2`** (from `test/test-mcp.py`):
- Replace `"CloudNativePG"` → `"{{ server_name }}"`

**`templates/Makefile.j2`** (from `Makefile`):
- Replace image name, registry, helm release name

---

## Phase 2: Extract Patterns

Create markdown documentation with embedded code examples in `patterns/`.

### `patterns/tool_implementation.md`

Extract from `cnpg_tools.py`:
- **`@with_mcp_context` decorator** - MUST be applied to every tool implementation
- **`MCPContext` class** - Wraps FastMCP Context, extracts user_id from JWT
- Function signature pattern with type hints
- Docstring format (Args, Returns, Examples, Error Handling sections)
- `asyncio.to_thread()` for Kubernetes calls
- `truncate_response()` usage
- `format_error_message()` pattern

**Critical Pattern - `with_mcp_context`**:
```python
from mcp_context import MCPContext, with_mcp_context

@with_mcp_context
async def my_tool(
    context: MCPContext,  # First param is ALWAYS MCPContext
    param1: str,
    namespace: Optional[str] = None
) -> str:
    """Tool docstring..."""
    # context.user_id available for user-scoped operations
    user_id = context.user_id
    ...
```

### `patterns/kubernetes_client.md`

Extract from `cnpg_tools.py`:
- Lazy client initialization pattern
- `get_kubernetes_clients()` function
- `get_current_namespace()` function
- CRD CRUD operations (list, get, create, patch, delete)

### `patterns/secret_management.md`

Extract from `cnpg_tools.py`:
- Creating secrets with generated passwords
- Reading secrets
- Secret naming conventions (`{cluster}-{role}`)

### `patterns/test_plugin.md`

Extract from `test/plugins/__init__.py` and example plugins:
- `TestPlugin` base class
- `TestResult` dataclass
- `depends_on` vs `run_after`
- `check_for_operational_error()`

### `patterns/helm_rbac.md`

Extract from `chart/templates/rolebinding.yaml`:
- Binding to operator-provided ClusterRoles
- Creating Role for secrets access
- Pattern for multi-namespace support

### `patterns/helm_chart.md`

Document the chart creation workflow:
- Start with `helm create {chart-name}`
- Add Redis dependency for OAuth session storage
- Run `helm dependency update` after modifying Chart.yaml
- Key modifications to default helm create output

---

## Phase 3: Build MCP Server

### `src/mcp_base_server.py`

```python
#!/usr/bin/env python3
"""
MCP-Base Server

MCP server that helps AI agents construct Kubernetes-Python MCP servers.
Exposes templates, patterns, and scaffolding tools via HTTP.
"""

import os
import logging
from pathlib import Path

from fastmcp import FastMCP, Context
import uvicorn
from jinja2 import Environment, FileSystemLoader

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP
mcp = FastMCP("mcp-base")

# Template directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
PATTERNS_DIR = Path(__file__).parent.parent / "patterns"

# Jinja2 environment
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    trim_blocks=True,
    lstrip_blocks=True
)

# =============================================================================
# Resources
# =============================================================================

@mcp.resource("template://server/{name}")
async def get_server_template(name: str) -> str:
    """Get a server template file."""
    # ... implementation

@mcp.resource("template://helm/{name}")
async def get_helm_template(name: str) -> str:
    """Get a Helm chart template file."""
    # ... implementation

@mcp.resource("pattern://{category}/{name}")
async def get_pattern(category: str, name: str) -> str:
    """Get a pattern documentation file."""
    # ... implementation

# =============================================================================
# Tools
# =============================================================================

@mcp.tool()
async def list_templates() -> str:
    """List all available templates."""
    # ... implementation

@mcp.tool()
async def list_patterns() -> str:
    """List all available patterns."""
    # ... implementation

@mcp.tool()
async def render_template(
    template_path: str,
    variables: dict
) -> str:
    """
    Render a Jinja2 template with provided variables.

    Args:
        template_path: Path like "server/entry_point.py.j2"
        variables: Dict of template variables

    Returns:
        Rendered template content
    """
    # ... implementation

@mcp.tool()
async def scaffold_project(
    server_name: str,
    server_description: str,
    k8s_api_group: str,
    k8s_api_version: str = "v1",
    k8s_crd_plural: str = "",
    port: int = 4204
) -> str:
    """
    Generate a complete MCP server project structure.

    Args:
        server_name: Hyphenated name (e.g., "cnpg-mcp")
        server_description: One-line description
        k8s_api_group: Kubernetes API group (e.g., "postgresql.cnpg.io")
        k8s_api_version: API version (default: "v1")
        k8s_crd_plural: CRD plural name (e.g., "clusters")
        port: HTTP server port (default: 4204)

    Returns:
        Summary of generated files
    """
    # ... implementation

@mcp.tool()
async def generate_tool_stub(
    tool_name: str,
    operation: str,
    crd_plural: str,
    description: str
) -> str:
    """
    Generate a tool implementation stub.

    Args:
        tool_name: Function name (e.g., "list_postgres_clusters")
        operation: One of "list", "get", "create", "update", "delete"
        crd_plural: CRD plural name
        description: Tool description

    Returns:
        Python code for the tool implementation
    """
    # ... implementation

@mcp.tool()
async def generate_test_plugin(
    tool_name: str,
    description: str,
    depends_on: list[str] = None
) -> str:
    """
    Generate a test plugin for a tool.

    Args:
        tool_name: Name of the tool to test
        description: Test description
        depends_on: List of test names this depends on

    Returns:
        Python code for the test plugin
    """
    # ... implementation

# =============================================================================
# HTTP Server
# =============================================================================

def create_app():
    """Create the HTTP application."""
    app = mcp.http_app(transport="streamable-http", path="/mcp")

    # Health endpoints
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def health(request):
        return JSONResponse({"status": "healthy"})

    app.routes.append(Route("/healthz", health))
    app.routes.append(Route("/readyz", health))

    return app


def main():
    """Main entry point."""
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting mcp-base server on {host}:{port}")

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
```

---

## Phase 4: MCP Resources

### Resource URI Scheme

```
template://server/entry-point      → templates/server/entry_point.py.j2
template://server/tools            → templates/server/tools.py.j2
template://server/mcp-context      → templates/server/mcp_context.py
template://server/auth-oidc        → templates/server/auth_oidc.py
template://server/auth-fastmcp     → templates/server/auth_fastmcp.py.j2
template://server/user-hash        → templates/server/user_hash.py
template://container/dockerfile    → templates/container/Dockerfile.j2
template://container/requirements  → templates/container/requirements.txt
template://helm/chart              → templates/helm/Chart.yaml.j2
template://helm/values             → templates/helm/values.yaml.j2
template://helm/deployment         → templates/helm/templates/deployment.yaml.j2
template://helm/service            → templates/helm/templates/service.yaml.j2
template://helm/configmap          → templates/helm/templates/configmap.yaml.j2
template://helm/rolebinding        → templates/helm/templates/rolebinding.yaml.j2
template://helm/serviceaccount     → templates/helm/templates/serviceaccount.yaml.j2
template://helm/ingress            → templates/helm/templates/ingress.yaml.j2
template://helm/hpa                → templates/helm/templates/hpa.yaml.j2
template://helm/helpers            → templates/helm/templates/_helpers.tpl.j2
template://test/runner             → templates/test/test_runner.py.j2
template://test/plugin-base        → templates/test/plugin_base.py
template://test/get-user-token     → templates/test/get_user_token.py
template://test/auth-proxy         → templates/test/auth_proxy.py
template://bin/create-secrets      → templates/bin/create_secrets.py.j2
template://bin/setup-auth0         → templates/bin/setup_auth0.py
template://bin/setup-rbac          → templates/bin/setup_rbac.py.j2
template://makefile                → templates/Makefile.j2

pattern://tool/implementation      → patterns/tool_implementation.md
pattern://kubernetes/client        → patterns/kubernetes_client.md
pattern://kubernetes/secrets       → patterns/secret_management.md
pattern://test/plugin              → patterns/test_plugin.md
pattern://helm/rbac                → patterns/helm_rbac.md
pattern://helm/chart               → patterns/helm_chart.md
```

---

## Phase 5: Tools Summary

| Tool | Purpose |
|------|---------|
| `list_templates` | List all available template files |
| `list_patterns` | List all available pattern documents |
| `render_template` | Render a Jinja2 template with variables |
| `scaffold_project` | Generate complete project structure |
| `generate_tool_stub` | Generate a single tool implementation |
| `generate_test_plugin` | Generate a test plugin for a tool |

---

## Template Variables

| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `server_name` | str | Hyphenated name | `cnpg-mcp` |
| `server_name_snake` | str | Python module name | `cnpg_mcp` |
| `server_name_class` | str | PascalCase name | `CnpgMcp` |
| `server_description` | str | One-line description | `PostgreSQL cluster management` |
| `port` | int | HTTP port | `4204` |
| `k8s_api_group` | str | CRD API group | `postgresql.cnpg.io` |
| `k8s_api_version` | str | CRD version | `v1` |
| `k8s_crd_plural` | str | CRD plural | `clusters` |
| `operator_cluster_roles` | list | ClusterRoles to bind | `["cnpg-cloudnative-pg-edit"]` |
| `tools` | list | Tool definitions | See below |

### Tool Definition

```python
{
    "name": "list_postgres_clusters",
    "description": "List all PostgreSQL clusters",
    "operation": "list",  # list, get, create, update, delete
    "crd_plural": "clusters",
    "parameters": [
        {"name": "namespace", "type": "Optional[str]", "default": "None"},
        {"name": "format", "type": "Literal['text', 'json']", "default": "'text'"}
    ]
}
```

---

## Implementation Order

1. **Create directory structure** (`templates/`, `patterns/`, `src/`)
2. **Copy as-is files** (7 files)
3. **Create Jinja2 templates** (12+ files)
4. **Extract patterns** (5 markdown files)
5. **Implement `mcp_base_server.py`** with resources and tools
6. **Create mcp-base's own Dockerfile and requirements.txt**
7. **Test with MCP Inspector**

---

## Success Criteria

An AI agent using mcp-base should be able to:

1. **Browse templates**: `list_templates` → see all available templates
2. **Read patterns**: Access `pattern://tool/implementation` to understand patterns
3. **Scaffold a project**: `scaffold_project(server_name="my-mcp", ...)` → complete structure
4. **Generate tools**: `generate_tool_stub(tool_name="list_resources", operation="list", ...)`
5. **Render templates**: `render_template("server/entry_point.py.j2", {...})` → valid Python

The generated MCP server should:
- Run via HTTP (Streamable HTTP transport)
- Authenticate with OIDC/Auth0
- Deploy to Kubernetes via Helm
- Pass automated tests
