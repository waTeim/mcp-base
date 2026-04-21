# mcp-base

An MCP server that helps AI agents build production-ready MCP servers for Kubernetes environments.

## What It Does

**mcp-base** exposes templates, patterns, and tools via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) that enable AI agents to generate complete, deployable MCP server projects. Generated servers include:

- FastMCP-based HTTP server with OAuth authentication
- Test server with direct OIDC authentication
- Helm chart with Redis session storage
- Plugin-based test framework
- Docker container build
- Kubernetes RBAC configuration
- Versioned prompt management with ConfigMap storage and hot-reload

## Quick Start

### 1. Run mcp-base

```bash
# Clone and install
git clone https://github.com/your-org/mcp-base.git
cd mcp-base
pip install -r requirements.txt

# Start server
python src/mcp_base_server.py --port 4207
```

### 2. Connect with Claude Desktop

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-base": {
      "url": "http://localhost:4207/mcp"
    }
  }
}
```

### 3. Generate a Server

Ask Claude:
> "Use mcp-base to generate an MCP server called 'My Kubernetes Manager' that manages pods"

Or call the tool directly:
```
generate_server_scaffold(server_name="My Kubernetes Manager")
```

## Features

### ⚠️ Resources vs Tools - Critical Distinction

**Reading resources does NOT create files. You must call tools to generate actual source code.**

- **Resources** provide read-only templates and documentation
- **Tools** actually generate and write files to disk

### Resources (Read-Only - Informational)

Resources return template content or documentation as strings. Reading them creates **NO files on disk**.

| URI | Description |
|-----|-------------|
| `pattern://generation-workflow` | **⚠️ Generation workflow (Resources vs Tools)** |
| `pattern://architecture` | Architecture overview and design patterns |
| `pattern://fastmcp-tools` | Tool implementation patterns |
| `pattern://authentication` | Auth0/OIDC setup guide |
| `pattern://testing` | Test framework patterns |
| `pattern://prompt-management` | Versioned prompts with ConfigMap and hot-reload |
| `template://server/*` | Server code templates (as strings) |
| `template://helm/*` | Helm chart templates (as strings) |
| `template://container/*` | Docker build templates (as strings) |

### Tools (Scaffold Generation)

Tools generate scaffold artifacts and return resource references. Use
`resources/read` with `scaffold://` URIs to retrieve content and write files
to disk.

| Tool | Description | Creates Files? |
|------|-------------|----------------|
| `generate_server_scaffold` | **Generate complete MCP server project scaffold (artifacts)** | ❌ No - returns artifact references |
| `list_artifacts` | List all files in a generated project | ❌ No - returns JSON list |
| `render_template` | Render individual template to string | ⚠️ Returns string - you must write it |
| `list_templates` | List available templates | ❌ No |
| `list_patterns` | List pattern documentation | ❌ No |
| `get_pattern` | Get specific pattern docs | ❌ No |

## Generated Server Structure

```
my-server/
├── src/
│   ├── my_server.py           # Main server (OAuth)
│   ├── my_test_server.py      # Test server (OIDC)
│   ├── my_server_tools.py     # Shared tools & resources
│   ├── auth_fastmcp.py        # OAuth provider
│   ├── auth_oidc.py           # OIDC middleware
│   ├── mcp_context.py         # User context extraction
│   └── prompt_registry.py     # Versioned prompt management
├── bin/                       # Configuration scripts
│   └── configure-make.py     # Generate make.env for Makefile
├── test/
│   ├── plugins/               # Test plugins
│   ├── test-mcp.py           # Test runner
│   └── get-user-token.py     # Token acquisition
├── chart/                     # Helm chart
├── Dockerfile
├── Makefile
└── requirements.txt
```

### Scaffold vs CLI Scripts

**In scaffold (`bin/`):**

| Script | Purpose |
|--------|---------|
| `configure-make.py` | Generate make.env for Makefile configuration |

**Via mcp-base CLI** (install with `pip install mcp-base`):

| Command | Purpose |
|---------|---------|
| `mcp-base setup-oidc` | Configure OIDC provider (Auth0, Dex, Keycloak, etc.) |
| `mcp-base create-secrets` | Create Kubernetes secrets |
| `mcp-base add-user` | Add users with assigned roles |
| `mcp-base setup-rbac` | Set up Kubernetes RBAC resources |

## Configuration Options

### generate_server_scaffold

```python
generate_server_scaffold(
    server_name="My MCP Server",      # Required: Human-readable name
    port=4207,                         # HTTP port (default: 4207)
    default_namespace="default",       # K8s namespace (default: "default")
    operator_cluster_roles="role1,role2",  # ClusterRoles to bind
    include_helm=True,                 # Include Helm chart
    include_test=True,                 # Include test framework
    include_bin=True,                  # Include utility scripts
    output_description="summary"       # "summary" or "full"
)
```

### render_template

```python
render_template(
    template_path="server/entry_point.py.j2",
    server_name="My Server",
    port=4207,
    default_namespace="default"
)
```

## Deployment

### Local Development

```bash
# Main server (OAuth)
python src/mcp_base_server.py --port 4207

# Health check
curl http://localhost:4207/healthz
```

### Docker

```bash
docker build -t mcp-base .
docker run -p 4207:4207 mcp-base
```

### Kubernetes with Helm

```bash
# Configure
cp chart/values.yaml chart/my-values.yaml
# Edit my-values.yaml with your Auth0 credentials

# Deploy
helm install mcp-base chart/ -f chart/my-values.yaml
```

## Authentication Setup

Generated servers use Auth0 for authentication. Required configuration:

1. **Create Auth0 Application** (Machine-to-Machine or SPA)
2. **Create Auth0 API** with appropriate scopes
3. **Configure environment variables:**

```bash
export OIDC_ISSUER="https://your-tenant.auth0.com"
export OIDC_AUDIENCE="https://your-api-identifier"
export AUTH0_CLIENT_ID="your-client-id"
export AUTH0_CLIENT_SECRET="your-client-secret"  # For M2M only
```

Or use the setup script:
```bash
python bin/setup-auth0.py --token YOUR_MANAGEMENT_API_TOKEN
```

## Testing Generated Servers

```bash
# Get user token (opens browser)
./test/get-user-token.py

# Run tests against test server
./test/test-mcp.py --url http://localhost:8001/test \
    --token-file /tmp/user-token.txt

# Output formats
./test/test-mcp.py --url http://localhost:8001/test \
    --output results.json --format json

./test/test-mcp.py --url http://localhost:8001/test \
    --output results.xml --format junit
```

## Development Mode (No-Auth)

For rapid development, debugging, and testing new features without authentication overhead, both mcp-base and generated servers support a **no-auth mode**.

### When to Use No-Auth Mode

- **Adding new features** - Test new tools/resources without auth setup
- **Debugging issues** - Isolate problems from authentication concerns
- **CI/CD pipelines** - Run automated tests without credentials
- **Local development** - Quick iteration without browser auth flow
- **AI agent testing** - Allow AI assistants to test changes directly

### Starting the Server (No-Auth)

```bash
# mcp-base test server
python src/mcp_base_test_server.py --no-auth --port 8001

# With custom identity (for user-specific testing)
python src/mcp_base_test_server.py --no-auth --identity "dev-user" --port 8001
```

### Running Tests (No-Auth)

```bash
# Test against no-auth server
./test/test-mcp.py --url http://localhost:8001/test --no-auth

# With debug logging for troubleshooting
./test/test-mcp.py --url http://localhost:8001/test --no-auth \
    --debug-log /tmp/mcp-debug.log
```

### How No-Auth Mode Works

1. **Server side**: `NoAuthMiddleware` replaces OIDC middleware and injects mock user claims
2. **Test runner**: `--no-auth` flag skips token acquisition
3. **Identity preserved**: Tools that need user context still receive a mock identity

Mock claims provided:
- `sub`, `preferred_username`, `name` → identity value (default: "test-user")
- `email` → `{identity}@test.local`
- `iss` → `http://localhost/no-auth`
- `scope` → `openid profile email`

### Debug Logging

For diagnosing test failures, enable debug logging:

```bash
./test/test-mcp.py --url http://localhost:8001/test --no-auth \
    --debug-log /tmp/mcp-debug.log

# View the detailed request/response log
cat /tmp/mcp-debug.log
```

The debug log captures all MCP protocol interactions with full request arguments and response data.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed documentation on:

- Dual-server pattern (Main + Test servers)
- Shared tools module architecture
- Authentication flows
- MCP protocol type handling
- Common pitfalls and solutions

## Key Design Decisions

1. **Dual Servers**: Separate OAuth (production) and OIDC (testing) endpoints enable headless automated testing while maintaining full OAuth security for production.

2. **Shared Tools Module**: Both servers import from a single `*_tools.py` file ensuring identical behavior.

3. **Plugin-Based Testing**: Tests are discovered automatically from `test/plugins/test_*.py` files.

4. **Redis Session Storage**: MCP tokens are stored encrypted in Redis for scalability.

## Development

### Adding Templates

1. Create `.j2` file in `templates/`
2. Register resource in `src/mcp_base_tools.py`
3. Add to scaffold generation if needed

### Adding Patterns

1. Create `.md` file in `patterns/`
2. Register resource in `src/mcp_base_tools.py`

### Running Tests

```bash
# With authentication
./test/get-user-token.py
./test/test-mcp.py --url http://localhost:8001/test \
    --token-file /tmp/user-token.txt
```

## Reference Implementation

See `example/cnpg-mcp/` for a complete working MCP server managing CloudNativePG PostgreSQL clusters.

## Resources

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Auth0 Documentation](https://auth0.com/docs)

## License

[Your License Here]
