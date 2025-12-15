# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mcp-base** is an MCP server that assists AI agents in constructing production-ready, Kubernetes-Python-centric remote MCP servers. It exposes templates, patterns, and tools via the MCP protocol.

**Key characteristics:**
- HTTP-only transport (Streamable HTTP via FastMCP)
- Jinja2 templates for parameterized code generation
- Pattern documentation for implementation guidance
- Tools for scaffolding complete MCP server projects

## ⚠️ CRITICAL: Resources vs Tools

**Reading a resource does NOT create files. You must call tools to generate actual code.**

### Resources (Read-Only - NO Files Created)
- `template://server/entry_point.py` - Returns template content as a string
- `pattern://fastmcp-tools` - Returns documentation as a string
- Reading these provides information but **writes nothing to disk**

### Tools (Actually Generate Files)
- `generate_server_scaffold()` - **Creates entire project directory with all files**
- `render_template()` - **Returns rendered template** (you must write it to disk)

**Common Mistake**: Agents read `template://server/entry_point.py` and conclude the source file has been created. It hasn't. The resource returns template content, but no file exists on disk until you:
1. Call `generate_server_scaffold()` to create the complete project, OR
2. Call `render_template()` and write the output to a file yourself

**Example workflow**:
```python
# ❌ WRONG - This only reads the template, creates NO files
template_content = await session.read_resource("template://server/entry_point.py")
# At this point, no files exist on disk!

# ✅ CORRECT - This creates all files
result = await session.call_tool("generate_server_scaffold", {
    "server_name": "My MCP Server"
})
# Now a complete project directory exists with all source files
```

## ⚠️ Bin Scripts Constraints

**The bin/ directory must contain ONLY Python scripts (.py). Shell scripts (.sh) are NOT allowed.**

### Required Bin Scripts

Generated servers include these utility scripts in `bin/`:

| Script | Purpose |
|--------|---------|
| `add-user.py` | Add Auth0 users with roles |
| `create-secrets.py` | Create Kubernetes secrets from auth0-config.json |
| `make-config.py` | Generate configuration files (auth0-config.json, helm-values.yaml) |
| `setup-auth0.py` | Configure Auth0 tenant (applications, APIs, roles) |
| `setup-rbac.py` | Set up Kubernetes RBAC resources |

**Do NOT generate shell scripts** like `run-local.sh`, `test-endpoints.sh`, etc. All utility scripts must be Python.

### Why Python Only?

1. **Portability**: Python scripts work consistently across Linux, macOS, and Windows
2. **Dependencies**: Can leverage existing Python packages (kubernetes, auth0-python)
3. **Error Handling**: Better exception handling and user feedback
4. **Consistency**: Same language as the MCP server itself

## Project Structure

```
mcp-base/
├── src/
│   └── mcp_base_server.py     # Main MCP server
├── templates/                  # Jinja2 templates
│   ├── server/                # Server code templates
│   ├── container/             # Dockerfile, requirements
│   ├── helm/                  # Helm chart templates
│   ├── test/                  # Test framework templates
│   └── bin/                   # Utility script templates
├── patterns/                   # Pattern documentation
│   ├── fastmcp-tools.md       # Tool implementation patterns
│   ├── authentication.md      # Auth0/OIDC patterns
│   ├── kubernetes-integration.md
│   ├── helm-chart.md
│   ├── testing.md
│   └── deployment.md
├── example/cnpg-mcp/          # Reference implementation
├── prompts/                   # Construction prompts
├── Dockerfile                 # Container build
└── requirements.txt           # Python dependencies
```

## Running the Server

```bash
# Install dependencies
pip install -r requirements.txt

# Run server (HTTP transport)
python src/mcp_base_server.py --port 8000

# Build and run container
docker build -t mcp-base .
docker run -p 8000:8000 mcp-base
```

## MCP Resources

The server exposes these resources:

### Template Resources (`template://`)
- `template://server/entry_point.py` - Main server entry point
- `template://server/auth_fastmcp.py` - FastMCP Auth0 provider
- `template://server/auth_oidc.py` - Generic OIDC provider
- `template://server/mcp_context.py` - MCPContext and with_mcp_context
- `template://server/user_hash.py` - User ID generation
- `template://server/tools.py` - Tool implementation skeleton
- `template://container/Dockerfile` - Container build
- `template://container/requirements.txt` - Python dependencies
- `template://helm/Chart.yaml` - Helm chart metadata
- `template://helm/values.yaml` - Default values
- `template://Makefile` - Build automation

### Pattern Resources (`pattern://`)
- `pattern://generation-workflow` - **⚠️ CRITICAL: MCP server generation workflow (Resources vs Tools)**
- `pattern://architecture` - **Architecture overview, design patterns, and common pitfalls**
- `pattern://fastmcp-tools` - FastMCP tool implementation
- `pattern://authentication` - Auth0/OIDC setup
- `pattern://kubernetes-integration` - K8s client patterns
- `pattern://helm-chart` - Helm chart creation
- `pattern://testing` - Test framework patterns (includes MCP SDK type handling)
- `pattern://deployment` - Production deployment

## MCP Tools

### `list_templates`
Lists all available templates with descriptions.

### `list_patterns`
Lists all available pattern documentation.

### `get_pattern(name)`
Retrieves full pattern documentation by name.

### `render_template(template_path, server_name, ...)`
Renders a single template with parameters:
- `template_path`: Path to template (e.g., "server/entry_point.py.j2")
- `server_name`: Human-readable server name
- `port`: HTTP port (default: 8000)
- `default_namespace`: K8s namespace (default: "default")
- `chart_name`: Helm chart name (defaults from server_name)
- `operator_cluster_roles`: Comma-separated ClusterRoles to bind

### `generate_server_scaffold(server_name, ...)`
Generates complete MCP server project:
- `server_name`: Human-readable server name
- `output_description`: "full" or "summary"
- `port`: HTTP port
- `default_namespace`: Default K8s namespace
- `operator_cluster_roles`: ClusterRoles to bind
- `include_helm`: Include Helm chart (default: true)
- `include_test`: Include test framework (default: true)
- `include_bin`: Include utility scripts (default: true)

## Template Variables

Templates use these Jinja2 variables:
- `{{ server_name }}` - Human-readable name
- `{{ server_name_snake }}` - snake_case version
- `{{ server_name_kebab }}` - kebab-case version
- `{{ server_name_pascal }}` - PascalCase version
- `{{ port }}` - HTTP port number
- `{{ default_namespace }}` - Default K8s namespace
- `{{ chart_name }}` - Helm chart name
- `{{ operator_cluster_roles }}` - List of ClusterRoles

## Usage Example

When an AI agent wants to create a new MCP server:

```python
# 1. List available templates
result = await mcp.call_tool("list_templates")

# 2. Get pattern documentation
pattern = await mcp.call_tool("get_pattern", {"name": "fastmcp-tools"})

# 3. Generate complete project
scaffold = await mcp.call_tool("generate_server_scaffold", {
    "server_name": "CloudNativePG MCP",
    "port": 8000,
    "operator_cluster_roles": "cnpg-cloudnative-pg-edit"
})

# 4. Or render individual template
template = await mcp.call_tool("render_template", {
    "template_path": "server/entry_point.py.j2",
    "server_name": "My MCP Server"
})
```

## Key Patterns from Reference Implementation

### Tool Implementation
```python
@mcp.tool(name="my_tool")
@with_mcp_context
async def my_tool(ctx: MCPContext, param: str) -> str:
    """Tool description for LLM consumption."""
    user = ctx.preferred_username or ctx.user_id
    await ctx.info(f"User {user} calling my_tool")

    result = await asyncio.to_thread(k8s_api.method, ...)
    return truncate_response(format_result(result))
```

### Authentication Flow
1. FastMCP Auth0Provider handles OAuth
2. Redis stores session tokens (encrypted with Fernet)
3. MCPContext extracts user info from JWT
4. with_mcp_context decorator wraps tools

### Helm Chart Structure
- Created via `helm create` then modified
- Redis dependency for session storage
- ConfigMap for OIDC config
- Secrets for Auth0 credentials
- RoleBinding to operator ClusterRoles

## Development

### Adding Templates
1. Create `.j2` file in `templates/`
2. Add resource function in `mcp_base_server.py`
3. Include in `generate_server_scaffold` if needed

### Adding Patterns
1. Create `.md` file in `patterns/`
2. Add resource function in `mcp_base_server.py`
3. Update `list_patterns` tool

## Critical Testing Considerations

### MCP Protocol Type Handling

When testing MCP servers generated by mcp-base, be aware of these critical details:

#### URI Type Conversion in Tests
The MCP SDK returns `Resource` objects with `uri` as a Pydantic `AnyUrl` type, not a plain string. When comparing URIs in tests:

```python
# ❌ WRONG - AnyUrl objects won't match strings
resource_uris = [r.uri for r in result.resources]
missing = ["template://server/entry_point.py" in resource_uris]  # Always False!

# ✅ CORRECT - Convert to strings
resource_uris = [str(r.uri) for r in result.resources]
missing = ["template://server/entry_point.py" in resource_uris]  # Works!
```

**Why this matters**: Without `str()` conversion, URI comparisons will silently fail, causing tests to report "Missing X resources" even when resources are correctly registered.

#### Test Content Expectations
Test assertions must match actual file content exactly:

```python
# If pattern file says "# FastMCP Tool Implementation Pattern"
expected_markers = [
    "# FastMCP Tool Implementation Pattern",  # ✅ Exact match
    "@mcp.tool",
]

# Not:
expected_markers = [
    "# FastMCP Tools",  # ❌ Won't match - wrong text
]
```

#### MCP Protocol Response Structure
- `session.list_resources()` returns `ListResourcesResult` with `.resources` attribute
- `session.read_resource()` returns `ReadResourceResult` with `.contents` attribute
- `session.list_prompts()` returns `ListPromptsResult` with `.prompts` attribute

Always check for attribute existence using `hasattr()` for defensive coding.

### Test Authentication
Generated servers support two auth modes:

1. **Main Server** (port 8000): FastMCP OAuth proxy issuing MCP tokens
   - Uses Auth0 for authentication
   - Issues its own MCP tokens for client access
   - Session tokens stored in Redis

2. **Test Server** (port 8001): Standard OIDC accepting Auth0 JWT tokens
   - Accepts Auth0 JWT tokens directly
   - No MCP token issuance
   - Used for automated testing

For testing, use the test server endpoint (`/test`) with Auth0 JWT tokens obtained via:
```bash
./test/get-user-token.py
./test/test-mcp.py --url http://localhost:8001/test --token-file /tmp/user-token.txt
```

### Source Code Organization
Generated servers follow this pattern:

```
my-mcp-server/
├── my_mcp_server.py          # Main server (FastMCP OAuth)
├── my_mcp_test_server.py     # Test server (OIDC)
├── my_mcp_tools.py            # Shared tool implementations
│   ├── register_resources()  # MCP resource registration
│   └── register_tools()       # MCP tool registration
├── auth_fastmcp.py            # FastMCP OAuth provider
├── auth_oidc.py               # Generic OIDC authentication
├── mcp_context.py             # Context and decorator
├── user_hash.py               # User ID utilities
└── test/
    └── plugins/
        ├── test_list_resources.py   # ✅ Uses str(r.uri)
        ├── test_read_resource.py    # ✅ Matches actual content
        └── test_list_prompts.py
```

Both server entry points import and call `register_resources()` and `register_tools()` to share the same tool implementations.

## Reference Implementation

The `example/cnpg-mcp/` directory contains a complete working MCP server for CloudNativePG management. Use it as a reference for:
- Tool implementation structure
- Authentication setup
- Helm chart organization
- Test framework usage
- Proper URI type handling in tests

## Resources

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
