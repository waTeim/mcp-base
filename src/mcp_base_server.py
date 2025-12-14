#!/usr/bin/env python3
"""
MCP Base Server - Entry Point

An MCP server that assists AI agents in constructing production-ready,
Kubernetes-Python-centric remote MCP servers.

This server provides:
- Resources: Templates, patterns, and documentation for building MCP servers
- Tools: Generate server scaffolding, helm charts, and configuration files

Transport: HTTP only (Streamable HTTP via FastMCP)

Tool implementations are in mcp_base_tools.py
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from fastmcp import FastMCP

# Import tool registration from tools module
from mcp_base_tools import register_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:     %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)

# Custom filter to exclude health check endpoints from access logs
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Exclude health check paths from access logs
        return not any(path in record.getMessage() for path in ["/healthz", "/readyz", "/health"])

# ============================================================================
# Path Configuration
# ============================================================================

# Base directory (parent of src/)
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
PATTERNS_DIR = BASE_DIR / "patterns"

# ============================================================================
# FastMCP Server
# ============================================================================

mcp = FastMCP(
    "mcp-base",
    instructions="""
You are an MCP server construction assistant. You help AI agents build
production-ready MCP servers for Kubernetes environments.

Available resources:
- Templates for server code, Dockerfile, Helm charts
- Pattern documentation for authentication, tools, deployment

Available tools:
- generate_server_scaffold: Create complete server project structure
- render_template: Render individual templates with parameters
- list_templates: List available templates
- get_pattern: Get pattern documentation

When building a new MCP server:
1. Use list_templates to see available templates
2. Use get_pattern to understand implementation patterns
3. Use generate_server_scaffold to create the project
4. Customize the generated files for your specific use case
"""
)

# ============================================================================
# Resources: Templates
# ============================================================================

@mcp.resource("template://server/entry_point.py")
def get_entry_point_template() -> str:
    """Server entry point template (HTTP transport)."""
    template_path = TEMPLATES_DIR / "server" / "entry_point.py.j2"
    return template_path.read_text()


@mcp.resource("template://server/auth_fastmcp.py")
def get_auth_fastmcp_template() -> str:
    """FastMCP Auth0 provider configuration template."""
    template_path = TEMPLATES_DIR / "server" / "auth_fastmcp.py.j2"
    return template_path.read_text()


@mcp.resource("template://server/auth_oidc.py")
def get_auth_oidc() -> str:
    """Generic OIDC authentication provider (as-is)."""
    template_path = TEMPLATES_DIR / "server" / "auth_oidc.py"
    return template_path.read_text()


@mcp.resource("template://server/mcp_context.py")
def get_mcp_context() -> str:
    """MCPContext class and with_mcp_context decorator (as-is)."""
    template_path = TEMPLATES_DIR / "server" / "mcp_context.py"
    return template_path.read_text()


@mcp.resource("template://server/user_hash.py")
def get_user_hash() -> str:
    """User ID generation utilities (as-is)."""
    template_path = TEMPLATES_DIR / "server" / "user_hash.py"
    return template_path.read_text()


@mcp.resource("template://server/tools.py")
def get_tools_template() -> str:
    """Tool implementation skeleton template."""
    template_path = TEMPLATES_DIR / "server" / "tools.py.j2"
    return template_path.read_text()


@mcp.resource("template://container/Dockerfile")
def get_dockerfile_template() -> str:
    """Container Dockerfile template."""
    template_path = TEMPLATES_DIR / "container" / "Dockerfile.j2"
    return template_path.read_text()


@mcp.resource("template://container/requirements.txt")
def get_requirements() -> str:
    """Python requirements.txt (as-is)."""
    template_path = TEMPLATES_DIR / "container" / "requirements.txt"
    return template_path.read_text()


@mcp.resource("template://helm/Chart.yaml")
def get_chart_yaml_template() -> str:
    """Helm Chart.yaml template with Redis dependency."""
    template_path = TEMPLATES_DIR / "helm" / "Chart.yaml.j2"
    return template_path.read_text()


@mcp.resource("template://helm/values.yaml")
def get_values_yaml_template() -> str:
    """Helm values.yaml template."""
    template_path = TEMPLATES_DIR / "helm" / "values.yaml.j2"
    return template_path.read_text()


@mcp.resource("template://Makefile")
def get_makefile_template() -> str:
    """Build automation Makefile template."""
    template_path = TEMPLATES_DIR / "Makefile.j2"
    return template_path.read_text()


# ============================================================================
# Resources: Patterns
# ============================================================================

@mcp.resource("pattern://fastmcp-tools")
def get_fastmcp_tools_pattern() -> str:
    """Pattern documentation for implementing FastMCP tools."""
    pattern_path = PATTERNS_DIR / "fastmcp-tools.md"
    return pattern_path.read_text()


@mcp.resource("pattern://authentication")
def get_authentication_pattern() -> str:
    """Pattern documentation for Auth0/OIDC authentication."""
    pattern_path = PATTERNS_DIR / "authentication.md"
    return pattern_path.read_text()


@mcp.resource("pattern://kubernetes-integration")
def get_kubernetes_pattern() -> str:
    """Pattern documentation for Kubernetes API integration."""
    pattern_path = PATTERNS_DIR / "kubernetes-integration.md"
    return pattern_path.read_text()


@mcp.resource("pattern://helm-chart")
def get_helm_chart_pattern() -> str:
    """Pattern documentation for Helm chart creation."""
    pattern_path = PATTERNS_DIR / "helm-chart.md"
    return pattern_path.read_text()


@mcp.resource("pattern://testing")
def get_testing_pattern() -> str:
    """Pattern documentation for testing MCP servers."""
    pattern_path = PATTERNS_DIR / "testing.md"
    return pattern_path.read_text()


@mcp.resource("pattern://deployment")
def get_deployment_pattern() -> str:
    """Pattern documentation for production deployment."""
    pattern_path = PATTERNS_DIR / "deployment.md"
    return pattern_path.read_text()


# ============================================================================
# Register Tools from tools module
# ============================================================================

register_tools(mcp)

# ============================================================================
# Server Entry Point
# ============================================================================

def run_http_transport(port: int = 4208, host: str = "0.0.0.0"):
    """Run the MCP server with HTTP transport."""
    import uvicorn
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    from auth_fastmcp import create_auth0_oauth_proxy, get_auth_config_summary, load_oidc_config_from_file

    logger.info("Initializing FastMCP OAuth Proxy for Auth0...")

    # Load configuration
    config = load_oidc_config_from_file() or {}
    issuer = config.get("issuer") or os.getenv("OIDC_ISSUER") or ""
    audience = config.get("audience") or os.getenv("OIDC_AUDIENCE") or ""
    client_id = config.get("client_id") or os.getenv("AUTH0_CLIENT_ID") or ""
    public_url = config.get("public_url") or os.getenv("PUBLIC_URL") or ""

    # Create OAuth Proxy (handles token issuance)
    auth_proxy = create_auth0_oauth_proxy()

    # Log configuration summary
    config_summary = get_auth_config_summary(issuer, audience, client_id, public_url)
    logger.info("=" * 80)
    logger.info("FastMCP OAuth Configuration:")
    logger.info("=" * 80)
    for key, value in config_summary.items():
        logger.info(f"  {key}: {value}")
    logger.info("=" * 80)

    # Set OAuth on mcp instance
    mcp.auth = auth_proxy

    async def health_check(request):
        """Health check endpoint."""
        return JSONResponse({"status": "healthy", "server": "mcp-base"})

    async def liveness_check(request):
        """Kubernetes liveness probe endpoint."""
        return JSONResponse({"status": "alive"})

    async def readiness_check(request):
        """Kubernetes readiness probe endpoint."""
        return JSONResponse({"status": "ready"})

    # Create app with OAuth at /mcp endpoint
    app = mcp.http_app(transport="http", path="/mcp")

    # Add health check routes
    app.add_route("/health", health_check, methods=["GET"])
    app.add_route("/healthz", liveness_check, methods=["GET"])
    app.add_route("/readyz", readiness_check, methods=["GET"])

    logger.info("")
    logger.info("=" * 80)
    logger.info("Server Configuration:")
    logger.info("=" * 80)
    logger.info(f"  Listening on: {host}:{port}")
    logger.info(f"  MCP Endpoint: /mcp")
    logger.info(f"  Auth: FastMCP OAuth Proxy (issues MCP tokens)")
    logger.info("  Tools: MCP server construction tools")
    logger.info(f"  OAuth Discovery: /.well-known/oauth-authorization-server")
    logger.info(f"  Client Registration: /register")
    logger.info("=" * 80)
    logger.info("")
    logger.info("To get an MCP token:")
    logger.info(f"  ./test/get-mcp-token.py --url http://{host}:{port}")
    logger.info("")
    logger.info("To test with MCP token:")
    logger.info("  ./test/test-mcp.py --transport http \\")
    logger.info(f"    --url http://{host}:{port}/mcp \\")
    logger.info("    --token-file /tmp/mcp-token.txt")
    logger.info("")

    # Add health check filter to uvicorn access logger
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

    uvicorn.run(app, host=host, port=port, log_level="info", ws="none")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MCP Base Server - Assists in constructing MCP servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run HTTP server (default)
  python mcp_base_server.py --port 4208

  # Run with custom host
  python mcp_base_server.py --host 127.0.0.1 --port 3000

Environment Variables:
  PORT        Default HTTP port (default: 4208)
  HOST        Default host binding (default: 0.0.0.0)
        """
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 4208)),
        help="HTTP server port (default: 4208)"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0)"
    )

    args = parser.parse_args()

    try:
        run_http_transport(port=args.port, host=args.host)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
