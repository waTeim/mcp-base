# MCP-Base Resource Analysis

Analysis of `example/cnpg-mcp/` to extract generic components that will be **embedded into mcp-base**.

> **Important**: After extraction, mcp-base will be self-contained. The `example/` directory is only used as the source for extraction - it will not exist at runtime.

---

## Extraction Strategy

```
example/cnpg-mcp/           mcp-base/
       │                         │
       │  ── extract ──►         │
       │                         ├── src/
       │                         │   └── mcp_base_server.py
       │                         │
       │                         ├── templates/        ◄── Parameterized templates
       │                         │   ├── server/
       │                         │   ├── container/
       │                         │   ├── helm/
       │                         │   ├── test/
       │                         │   └── bin/
       │                         │
       │                         └── patterns/         ◄── Code pattern documentation
       │                             ├── tool.md
       │                             ├── kubernetes.md
       │                             └── testing.md
```

---

## Files to Extract → Embed

### Templates Directory Structure

```
templates/
├── server/
│   ├── entry_point.py.j2      ◄── from cnpg_mcp_server.py (parameterized)
│   ├── tools.py.j2            ◄── from cnpg_tools.py (tool stubs, parameterized)
│   ├── mcp_context.py         ◄── from cnpg_tools.py lines 45-165 (as-is, fully generic)
│   ├── auth_oidc.py           ◄── from auth_oidc.py (as-is, fully generic)
│   ├── auth_fastmcp.py.j2     ◄── from auth_fastmcp.py (server name in logs)
│   └── user_hash.py           ◄── from user_hash.py (as-is, fully generic)
│
├── container/
│   ├── Dockerfile.j2          ◄── from Dockerfile (parameterized)
│   └── requirements.txt       ◄── from requirements.txt (as-is)
│
├── helm/
│   ├── Chart.yaml.j2
│   ├── values.yaml.j2
│   └── templates/
│       ├── _helpers.tpl.j2
│       ├── deployment.yaml.j2
│       ├── service.yaml.j2
│       ├── serviceaccount.yaml.j2
│       ├── configmap.yaml.j2
│       ├── ingress.yaml.j2
│       ├── hpa.yaml.j2
│       └── rolebinding.yaml.j2
│
├── test/
│   ├── test_runner.py.j2      ◄── from test-mcp.py (parameterized)
│   ├── plugin_base.py         ◄── from plugins/__init__.py (as-is)
│   ├── get_user_token.py      ◄── from get-user-token.py (as-is)
│   └── auth_proxy.py          ◄── from mcp-auth-proxy.py (as-is)
│
├── bin/
│   ├── create_secrets.py.j2   ◄── from create_secrets.py (parameterized)
│   ├── setup_auth0.py         ◄── from setup-auth0.py (as-is)
│   └── setup_rbac.py.j2       ◄── from setup_rbac.py (RBAC rules parameterized)
│
└── Makefile.j2                ◄── from Makefile (parameterized)
```

### Patterns Directory Structure

```
patterns/
├── tool_implementation.md     ◄── Extracted docstring + code patterns
│   - Function signature pattern
│   - Docstring format (Args, Returns, Examples, Error Handling)
│   - Async Kubernetes call pattern
│   - Error handling with format_error_message()
│   - Response truncation
│
├── kubernetes_client.md       ◄── Extracted patterns
│   - Lazy client initialization
│   - asyncio.to_thread() for blocking calls
│   - Namespace inference from context
│   - CRD CRUD operations
│
├── secret_management.md       ◄── Extracted patterns
│   - Creating secrets with passwords
│   - Reading secrets
│   - Secret naming conventions
│
├── test_plugin.md             ◄── Extracted patterns
│   - TestPlugin class structure
│   - depends_on vs run_after
│   - TestResult usage
│   - check_for_operational_error()
│
├── helm_rbac.md               ◄── Extracted patterns
│   - Binding to operator ClusterRoles
│   - Secrets Role for credential management
│
└── helm_chart.md              ◄── Chart creation pattern
    - Created via `helm create` then modified
    - Redis dependency for OAuth session storage
    - `helm dependency update` after Chart.yaml changes
```

---

## Template Variables

Templates use Jinja2 with these variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `server_name` | Hyphenated name | `cnpg-mcp` |
| `server_name_snake` | Python module name | `cnpg_mcp` |
| `server_name_class` | PascalCase | `CnpgMcp` |
| `server_description` | One-line description | `PostgreSQL cluster management via CloudNativePG` |
| `port` | HTTP server port | `4204` |
| `k8s_api_group` | CRD API group | `postgresql.cnpg.io` |
| `k8s_api_version` | CRD API version | `v1` |
| `k8s_crd_plural` | CRD plural name | `clusters` |
| `operator_cluster_roles` | List of ClusterRoles | `["cnpg-cloudnative-pg-edit"]` |
| `tools` | List of tool definitions | See below |

### Tool Definition Structure

```python
tools = [
    {
        "name": "list_postgres_clusters",
        "description": "List all PostgreSQL clusters",
        "operation": "list",
        "crd_plural": "clusters",
        "parameters": [
            {"name": "namespace", "type": "str", "optional": True},
            {"name": "format", "type": "Literal['text', 'json']", "default": "text"}
        ]
    },
    ...
]
```

---

## Resource URIs (Runtime)

When mcp-base runs, it exposes these resources:

```
# Templates - Return file contents with variable substitution
template://server/entry-point
template://server/auth-oidc
template://server/auth-fastmcp
template://server/user-hash
template://container/dockerfile
template://container/requirements
template://helm/chart
template://helm/values
template://helm/deployment
template://helm/service
template://helm/configmap
template://helm/rolebinding
... (all helm templates)
template://test/runner
template://test/plugin-base
template://test/get-user-token
template://bin/create-secrets
template://bin/setup-auth0
template://bin/setup-rbac
template://makefile

# Patterns - Return markdown documentation with code examples
pattern://tool/implementation
pattern://tool/crud-operations
pattern://tool/error-handling
pattern://kubernetes/async-client
pattern://kubernetes/namespace
pattern://kubernetes/secrets
pattern://test/plugin
pattern://helm/rbac-binding
pattern://helm/chart
```

---

## Fully Generic Files (Copy As-Is)

These require no parameterization:

| Source | Destination |
|--------|-------------|
| `src/auth_oidc.py` | `templates/server/auth_oidc.py` |
| `src/user_hash.py` | `templates/server/user_hash.py` |
| `src/cnpg_tools.py` (lines 45-165) | `templates/server/mcp_context.py` |
| `requirements.txt` | `templates/container/requirements.txt` |
| `test/plugins/__init__.py` | `templates/test/plugin_base.py` |
| `test/get-user-token.py` | `templates/test/get_user_token.py` |
| `test/mcp-auth-proxy.py` | `templates/test/auth_proxy.py` |
| `bin/setup-auth0.py` | `templates/bin/setup_auth0.py` |

---

## Parameterized Files (Convert to Jinja2)

These need variable substitution:

| Source | Variables to Extract |
|--------|---------------------|
| `src/cnpg_mcp_server.py` | `server_name`, tool imports/registrations |
| `src/auth_fastmcp.py` | `server_name` in log messages |
| `Dockerfile` | `server_name`, `entry_point`, `port` |
| `Makefile` | `server_name`, `registry`, `image_name` |
| `bin/create_secrets.py` | `server_name` |
| `bin/setup_rbac.py` | `server_name`, RBAC rules |
| `test/test-mcp.py` | `server_name` |
| `chart/Chart.yaml` | `chart_name`, `description`, `version` |
| `chart/values.yaml` | `server_name`, `port`, defaults |
| `chart/templates/*.yaml` | `chart_name` (in helper references) |

---

## Pattern Extraction

Patterns are documentation with embedded code examples, extracted from:

### MCPContext and with_mcp_context Decorator
Source: `src/cnpg_tools.py` lines 45-165

The `MCPContext` class wraps FastMCP's Context and extracts user identification from JWT claims. The `@with_mcp_context` decorator MUST be applied to every tool implementation.

```python
class MCPContext:
    """Extended MCP Context that includes user identification."""
    def __init__(self, ctx: FastMCPContext):
        self.ctx = ctx
        self.user_id: Optional[str] = None
        self.preferred_username: Optional[str] = None
        self.issuer: Optional[str] = None
        self._extract_user_info()

def with_mcp_context(func):
    """Decorator that wraps FastMCP Context into MCPContext."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Find FastMCP Context, wrap it, pass as first arg
        ...
    return wrapper
```

### Tool Implementation Pattern
Source: `src/cnpg_tools.py` lines 767+ (list_postgres_clusters)

```python
@with_mcp_context  # REQUIRED on every tool
async def list_postgres_clusters(
    context: MCPContext,  # First param is ALWAYS MCPContext
    namespace: Optional[str] = None,
    detail_level: Literal["concise", "detailed"] = "concise",
    format: Literal["text", "json"] = "text"
) -> str:
    """
    List all PostgreSQL clusters managed by CloudNativePG.

    Args:
        namespace: Filter by namespace (lists all if not specified)
        detail_level: 'concise' (default) or 'detailed'
        format: Output format - 'text' (human-readable) or 'json'

    Returns:
        Formatted list of clusters with status information

    Examples:
        - list_postgres_clusters() - List all clusters
        - list_postgres_clusters(namespace="production")

    Error Handling:
        - 403 Forbidden: Check RBAC permissions
        - Connection errors: Verify cluster connectivity
    """
    try:
        custom_api, _ = get_kubernetes_clients()

        if namespace:
            clusters = await asyncio.to_thread(
                custom_api.list_namespaced_custom_object,
                group=API_GROUP, version=API_VERSION,
                namespace=namespace, plural=CRD_PLURAL
            )
        else:
            clusters = await asyncio.to_thread(
                custom_api.list_cluster_custom_object,
                group=API_GROUP, version=API_VERSION, plural=CRD_PLURAL
            )

        return truncate_response(format_clusters(clusters, detail_level, format))

    except ApiException as e:
        return format_error_message(e, "listing clusters")
```

### Kubernetes Async Client Pattern
Source: `src/cnpg_tools.py` lines 50-80

```python
# Lazy initialization
custom_api: Optional[client.CustomObjectsApi] = None
core_api: Optional[client.CoreV1Api] = None

def get_kubernetes_clients():
    """Lazy initialization of Kubernetes clients."""
    global custom_api, core_api
    if custom_api is None:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        custom_api = client.CustomObjectsApi()
        core_api = client.CoreV1Api()
    return custom_api, core_api
```

---

## Summary

**mcp-base will contain:**
1. `templates/` - 25+ files (13 as-is, 12+ Jinja2)
2. `patterns/` - 5 markdown files with code examples
3. `src/mcp_base_server.py` - The MCP server itself

**The example/ directory is only used during initial development** to extract these artifacts. Once extracted and embedded, mcp-base is self-contained.
