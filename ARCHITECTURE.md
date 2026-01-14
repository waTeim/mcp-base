# MCP-Base Architecture

This document describes the architecture of mcp-base and the MCP servers it generates.

## Overview

**mcp-base** is an MCP server that assists AI agents in constructing production-ready, Kubernetes-Python-centric remote MCP servers. It uses a dual-server architecture pattern with shared tool implementations.

## Core Architectural Patterns

### 1. Dual-Server Architecture

Every generated MCP server includes two entry points serving different purposes:

```
┌─────────────────────────────────────────────────────────────┐
│                    Generated MCP Server                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────┐        │
│  │   Main Server       │    │   Test Server       │        │
│  │   (port 4207)       │    │   (port 8001)       │        │
│  │                     │    │                     │        │
│  │  FastMCP OAuth      │    │  Direct OIDC        │        │
│  │  Issues MCP tokens  │    │  Auth0 JWT tokens   │        │
│  │  Production use     │    │  Testing use        │        │
│  │  /mcp endpoint      │    │  /test endpoint     │        │
│  └──────────┬──────────┘    └──────────┬──────────┘        │
│             │                          │                    │
│             └──────────┬───────────────┘                    │
│                        │                                    │
│              ┌─────────▼─────────┐                          │
│              │   Shared Tools    │                          │
│              │   (*_tools.py)    │                          │
│              │                   │                          │
│              │ register_tools()  │                          │
│              │ register_resources()                         │
│              └───────────────────┘                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Why two servers?**
- **Main Server**: For production use with full OAuth flow. Issues MCP-specific tokens stored in Redis.
- **Test Server**: For automated testing. Accepts Auth0 JWT tokens directly, enabling headless test execution.

### 2. Shared Tools Module Pattern

Tool and resource implementations are centralized in a single `*_tools.py` module:

```python
# my_server_tools.py

def register_resources(mcp):
    """Register all resources with the MCP server instance."""

    @mcp.resource("config://server/settings")
    def get_server_settings() -> str:
        """Server configuration."""
        return json.dumps({"version": "1.0.0"})

    @mcp.resource("docs://api/reference")
    def get_api_reference() -> str:
        """API documentation."""
        return "# API Reference..."

def register_tools(mcp):
    """Register all tools with the MCP server instance."""

    @mcp.tool(name="my_tool")
    @with_mcp_context
    async def my_tool(ctx: MCPContext, param: str) -> str:
        """Tool description."""
        return await my_tool_impl(ctx, param)
```

Both server entry points import and call these functions:

```python
# In main server (my_server.py)
from my_server_tools import register_resources, register_tools
register_resources(mcp)
register_tools(mcp)

# In test server (my_test_server.py)
from my_server_tools import register_resources, register_tools
register_resources(mcp)
register_tools(mcp)
```

**Benefits:**
- Single source of truth for all tools and resources
- Both servers expose identical functionality
- Changes automatically apply to both servers

### 3. Authentication Architecture

#### Main Server (FastMCP OAuth Proxy)

```
┌──────────────┐     ┌─────────────────┐     ┌────────────┐
│   Client     │────▶│  FastMCP OAuth  │────▶│   Auth0    │
│              │     │     Proxy       │     │            │
│              │◀────│                 │◀────│            │
└──────────────┘     └─────────────────┘     └────────────┘
        │                    │
        │ MCP Token          │ Session Storage
        ▼                    ▼
   [API Access]         [Redis]
```

1. Client initiates OAuth flow via FastMCP
2. FastMCP redirects to Auth0 for authentication
3. Auth0 returns authorization code
4. FastMCP exchanges code for tokens
5. FastMCP issues its own MCP token to client
6. Session stored in Redis (Fernet encrypted)

#### Test Server (Direct OIDC)

```
┌──────────────┐     ┌─────────────────┐     ┌────────────┐
│ Test Client  │────▶│   Test Server   │────▶│   Auth0    │
│              │     │  (OIDC Auth)    │     │  (JWKS)    │
│ + JWT Token  │     │                 │     │            │
└──────────────┘     └─────────────────┘     └────────────┘
```

1. Test client obtains Auth0 JWT token directly (via browser or CLI)
2. Test client sends JWT in Authorization header
3. Test server validates JWT against Auth0 JWKS
4. No token issuance - direct pass-through authentication

#### No-Auth Mode (Development)

For rapid development, debugging, and CI/CD pipelines, the test server supports a **no-auth mode**:

```
┌──────────────┐     ┌─────────────────┐
│ Test Client  │────▶│   Test Server   │
│              │     │  (--no-auth)    │
│ (no token)   │     │                 │
└──────────────┘     └─────────────────┘
                            │
                            ▼
                     [NoAuthMiddleware]
                     Injects mock claims:
                     - sub, preferred_username
                     - email, iss, scope
```

**When to use no-auth mode:**
- Adding new features - Test quickly without auth setup
- Debugging issues - Isolate problems from authentication
- CI/CD pipelines - Run automated tests without credentials
- AI agent testing - Allow assistants to test changes directly

**Starting no-auth mode:**
```bash
# Start test server without authentication
python my_mcp_test_server.py --no-auth --port 8001

# Custom identity for user-specific testing
python my_mcp_test_server.py --no-auth --identity "dev-user" --port 8001

# Run tests without authentication
./test/test-mcp.py --url http://localhost:8001/test --no-auth
```

**Mock claims provided:**
- `sub`, `preferred_username`, `name` → identity value (default: "test-user")
- `email` → `{identity}@test.local`
- `iss` → `http://localhost/no-auth`
- `scope` → `openid profile email`

### 4. MCP Protocol Structure

Understanding the MCP SDK's type system is critical for testing:

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Protocol Types                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  session.list_resources()                                   │
│  └─▶ ListResourcesResult                                    │
│       └─▶ .resources: list[Resource]                        │
│            └─▶ .uri: AnyUrl  ← Pydantic type, NOT string!  │
│            └─▶ .name: str                                   │
│            └─▶ .description: str                            │
│                                                              │
│  session.read_resource(uri)                                 │
│  └─▶ ReadResourceResult                                     │
│       └─▶ .contents: list[ResourceContent]                  │
│            └─▶ .text: str                                   │
│                                                              │
│  session.list_prompts()                                     │
│  └─▶ ListPromptsResult                                      │
│       └─▶ .prompts: list[Prompt]                            │
│                                                              │
│  session.call_tool(name, arguments)                         │
│  └─▶ CallToolResult                                         │
│       └─▶ .content: list[ContentBlock]                      │
│            └─▶ .text: str                                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Critical: AnyUrl vs String Comparison**

The `Resource.uri` field is a Pydantic `AnyUrl` type, not a plain string. Direct string comparison will fail:

```python
# ❌ WRONG - Always returns False
"template://server/entry_point.py" == AnyUrl("template://server/entry_point.py")

# ❌ WRONG - Always returns False
"template://server/entry_point.py" in [r.uri for r in result.resources]

# ✅ CORRECT - Convert to string first
"template://server/entry_point.py" in [str(r.uri) for r in result.resources]
```

### 5. Resource Registration Pattern

Resources are registered using FastMCP's `@mcp.resource()` decorator:

```python
def register_resources(mcp):
    """Register all resources with the MCP server instance."""

    # Template resources (return file content)
    @mcp.resource("template://server/entry_point.py")
    def get_entry_point_template() -> str:
        """Server entry point template."""
        return Path("templates/server/entry_point.py.j2").read_text()

    # Pattern resources (return documentation)
    @mcp.resource("pattern://fastmcp-tools")
    def get_fastmcp_tools_pattern() -> str:
        """Pattern documentation for implementing FastMCP tools."""
        return Path("patterns/fastmcp-tools.md").read_text()

    # Config resources (return dynamic data)
    @mcp.resource("config://server/status")
    def get_server_status() -> str:
        """Current server status."""
        return json.dumps({"status": "healthy", "uptime": get_uptime()})
```

**Resource URI Schemes:**
- `template://` - Code templates and configuration files
- `pattern://` - Implementation pattern documentation
- `config://` - Dynamic configuration data
- `docs://` - API documentation and guides

### 6. Tool Implementation Pattern

Tools follow a consistent pattern with context injection:

```python
# 1. Implementation function (contains actual logic)
async def list_items_impl(ctx: MCPContext, namespace: str) -> str:
    """Implementation of list_items."""
    user = ctx.preferred_username or ctx.user_id
    await ctx.ctx.info(f"User {user} listing items in {namespace}")

    # Actual implementation...
    result = await k8s_api.list_items(namespace=namespace)
    return truncate_response(format_result(result))

# 2. Registration wrapper (decorators + delegation)
def register_tools(mcp):
    @mcp.tool(name="list_items")
    @with_mcp_context
    async def list_items(ctx: MCPContext, namespace: str = "default") -> str:
        """
        List all items in the specified namespace.

        Args:
            namespace: Kubernetes namespace to list from

        Returns:
            Formatted list of items
        """
        return await list_items_impl(ctx, namespace)
```

**Pattern Benefits:**
- `@mcp.tool()` handles schema generation from type hints
- `@with_mcp_context` extracts user context from JWT
- Separation allows unit testing of `_impl` functions

### 7. Prompt Management Architecture

Generated servers include a PromptRegistry for managing MCP prompts with versioning and hot-reload:

```
┌─────────────────────────────────────────────────────────────┐
│                   Prompt Management                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │  ConfigMap   │────▶│PromptRegistry│────▶│   FastMCP   │ │
│  │ (prompts.yaml)    │  (Python)    │     │  Prompts    │ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│        │                    │                               │
│        │ Hot-reload         │ SHA256 hashing               │
│        ▼                    ▼                               │
│   [File Watch]         [ETag Support]                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Features:**
- **Versioned bundles**: Semver versioning with SHA256 content hashing
- **ConfigMap storage**: Prompts defined in Kubernetes ConfigMap
- **Hot-reload**: Update prompts without server restart
- **Pydantic validation**: Schema enforcement for prompt definitions
- **Safety guardrails**: Detect prompt injection patterns

**Bundle Manifest Format:**
```yaml
version: "1.0.0"
updated_at: "2024-01-15T10:00:00Z"
prompts:
  - id: "example-prompt"
    name: "Example Prompt"
    description: "An example prompt template"
    template: |
      Process this request: {{ input }}
    arguments:
      - name: input
        description: "User input to process"
        required: true
```

**Admin Tools:**
- `admin_reload_prompts`: Trigger hot-reload from ConfigMap
- `admin_get_prompt_manifest`: Get version/hash for caching

### 8. Artifact Retrieval Architecture

Generated scaffolds are stored as in-memory artifacts and exposed via
`scaffold://{project_id}/{path}` resources. The retrieval flow is:

```
┌─────────────────────────────────────────────────────────────┐
│              Artifact Retrieval Flow                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Agent generates scaffold                                 │
│     generate_server_scaffold(...) → project_id              │
│                                                              │
│  2. Agent lists files                                        │
│     list_artifacts(project_id) → paths + scaffold URIs       │
│                                                              │
│  3. Agent reads files                                        │
│     resources/read("scaffold://{project_id}/{path}")         │
│                                                              │
│  4. Agent writes files to disk                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Notes:**
- `resources/read` returns full file content, so large files can consume
  context. Prefer targeted reads and avoid loading unnecessary files.

**Tools Provided:**
1. `list_artifacts(project_id)` - List all files in generated project
2. `resources/read` - Read `scaffold://{project_id}/{path}` to fetch file content

### 9. Test Plugin Architecture

Tests use a plugin-based architecture for extensibility:

```
test/
├── plugins/
│   ├── __init__.py              # TestPlugin base class, TestResult
│   ├── test_list_resources.py   # Tests resources/list endpoint
│   ├── test_read_resource.py    # Tests resources/read endpoint
│   ├── test_list_prompts.py     # Tests prompts/list endpoint
│   └── test_your_tool.py        # Tests custom tools
└── test-mcp.py                  # Test runner
```

**Test Plugin Structure:**

```python
class TestListResources(TestPlugin):
    tool_name = "list_resources"
    description = "Verifies server exposes expected resources"
    depends_on = []  # Tests that must pass first
    run_after = []   # Soft ordering preference

    async def test(self, session) -> TestResult:
        result = await session.list_resources()

        # CRITICAL: Convert AnyUrl to string for comparison
        resource_uris = [str(r.uri) for r in result.resources]

        expected = ["template://server/entry_point.py", ...]
        missing = [r for r in expected if r not in resource_uris]

        if missing:
            return TestResult(passed=False, message=f"Missing: {missing}")
        return TestResult(passed=True, message="All resources found")
```

## File Structure (Generated Servers)

```
my-mcp-server/
├── src/
│   ├── my_mcp_server.py         # Main entry point (FastMCP OAuth)
│   ├── my_mcp_test_server.py    # Test entry point (OIDC)
│   ├── my_mcp_tools.py          # Shared tools & resources
│   ├── auth_fastmcp.py          # FastMCP OAuth provider
│   ├── auth_oidc.py             # Generic OIDC middleware
│   ├── mcp_context.py           # MCPContext & with_mcp_context
│   ├── user_hash.py             # User ID utilities
│   └── prompt_registry.py       # Versioned prompt management
├── bin/                          # Configuration scripts
│   └── configure-make.py        # Generate make.env for Makefile
├── test/
│   ├── plugins/
│   │   ├── __init__.py          # Base classes
│   │   ├── test_list_resources.py
│   │   ├── test_read_resource.py
│   │   └── test_list_prompts.py
│   ├── test-mcp.py              # Test runner
│   └── get-user-token.py        # Token acquisition
├── chart/                        # Helm chart
├── Dockerfile
├── Makefile
└── requirements.txt
```

### Script Distribution

**In scaffold (`bin/`):**

| Script | Purpose |
|--------|---------|
| `configure-make.py` | Generate make.env for Makefile configuration |

**Via mcp-base CLI** (install with `pip install mcp-base`):

| Command | Purpose |
|---------|---------|
| `mcp-base setup-oidc` | Configure OIDC provider (Auth0, Dex, Keycloak, etc.) |
| `mcp-base create-secrets` | Create Kubernetes secrets |
| `mcp-base add-user` | Add users with roles |
| `mcp-base setup-rbac` | Set up Kubernetes RBAC resources |

**⚠️ IMPORTANT**: The `bin/` directory must contain ONLY Python scripts (`.py`). Shell scripts (`.sh`) are NOT allowed.

## Common Pitfalls & Solutions

### 1. URI Type Mismatch in Tests

**Problem:** Test reports "Missing N resources" when resources are registered correctly.

**Cause:** Comparing string URIs to `AnyUrl` objects.

**Solution:** Always convert URIs to strings:
```python
resource_uris = [str(r.uri) for r in result.resources]
```

### 2. Test Content Expectations

**Problem:** Test reports "Resource missing expected content" for valid resources.

**Cause:** Test expectation doesn't match actual file content.

**Solution:** Verify expected strings match the actual file:
```python
# If file contains "# FastMCP Tool Implementation Pattern"
expected_markers = ["# FastMCP Tool Implementation Pattern"]  # ✅
# Not
expected_markers = ["# FastMCP Tools"]  # ❌
```

### 3. Authentication Mode Confusion

**Problem:** Tests fail with authentication errors.

**Cause:** Using wrong token type for the server endpoint or mode.

**Solution:**
- Main server (`/mcp`): Use MCP tokens from OAuth flow
- Test server (`/test`): Use Auth0 JWT tokens directly
- No-auth mode: Start server with `--no-auth`, test with `--no-auth`

**Development workflow:**
```bash
# Server: python my_test_server.py --no-auth --port 8001
# Tests:  ./test/test-mcp.py --url http://localhost:8001/test --no-auth
```

### 4. Resource Registration Scope

**Problem:** Resources not visible to clients.

**Cause:** Registering resources in module scope instead of via `register_resources()`.

**Solution:** Always use the registration function pattern:
```python
# ❌ WRONG - Module-level registration
@mcp.resource("...")
def my_resource(): ...

# ✅ CORRECT - Via registration function
def register_resources(mcp):
    @mcp.resource("...")
    def my_resource(): ...
```

### 5. Path Resolution in Containers

**Problem:** Resources fail to load in container but work locally.

**Cause:** Hardcoded paths that don't account for container layout.

**Solution:** Use dynamic path resolution:
```python
_possible_base = Path(__file__).parent.parent
if not (_possible_base / "templates").exists():
    _possible_base = Path(__file__).parent
BASE_DIR = _possible_base
```

## Best Practices

1. **Always test both servers** - Main and test server should behave identically
2. **Convert Pydantic types** - Use `str()` for AnyUrl comparisons
3. **Match actual content** - Test expectations must match file content exactly
4. **Use defensive checks** - `hasattr(result, 'resources')` before accessing
5. **Centralize tools** - One `*_tools.py` module shared by both servers
6. **Log user context** - Include user info in all tool operations for audit
7. **Truncate responses** - Respect LLM context limits (~25K chars)
8. **Format errors helpfully** - Include actionable suggestions in error messages
