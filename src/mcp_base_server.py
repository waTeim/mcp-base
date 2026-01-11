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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

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
# FastMCP Server
# ============================================================================

mcp = FastMCP(
    "mcp-base",
    instructions="""
You are an MCP server construction assistant. You help AI agents build
production-ready MCP servers for Kubernetes environments.

========================================================================
PHASE 1: SCAFFOLD RETRIEVAL (MECHANICAL - NO CREATIVITY)
========================================================================

This phase is MECHANICAL work. Think: copy machine, not architect.
Think: assembling IKEA furniture - follow instructions exactly.

Step 1: Generate scaffold
   result = generate_server_scaffold(server_name="My Server")
   project_id = result["project_id"]
   files_list = result["files"]  # e.g., 33 files

Step 2: Retrieve and write EVERY file (no exceptions)
   for each file_path in files_list:
       content = get_artifact(project_id, file_path)
       write content to ./file_path (EXACT content, no modifications)

Step 3: Verify file count
   Count files written. Must match len(files_list).

CRITICAL - DO NOT during Phase 1:
- Write custom content instead of using get_artifact results
- Use bash heredocs to "save time"
- Skip files thinking "I'll write these faster myself"
- Start customizing before ALL scaffold files are written
- Create documentation before scaffold is complete
- Get distracted by other tasks

These are common failure modes caused by impatience/eagerness.
If you catch yourself doing any of these, STOP.

========================================================================
PHASE 2: CUSTOMIZATION (ONLY AFTER PHASE 1 COMPLETE)
========================================================================

Only after ALL files are written to disk:
- Customize the *_tools.py file for your specific functionality
- Add any additional dependencies to requirements.txt
- Modify Helm values as needed

========================================================================
CHECKPOINT
========================================================================

Before proceeding to Phase 2, verify:
[ ] All files from files_list retrieved via get_artifact
[ ] All files written to current directory (.)
[ ] No custom content written (only scaffold content)
[ ] File count matches expected count

Available tools:
- generate_server_scaffold: Create complete server project structure
- get_artifact: Retrieve a specific file from a generated scaffold
- list_artifacts: List all files in a scaffold project
- render_template: Render individual templates with parameters
- list_templates: List available templates
- get_pattern: Get pattern documentation

NOTE: Utility scripts are available via the mcp-base CLI:
  pip install mcp-base
  mcp-base --help  # Shows: add-user, create-secrets, make-config, setup-oidc, setup-rbac
"""
)

# ============================================================================
# Register Resources and Tools from tools module
# ============================================================================

from mcp_base_tools import register_resources

register_resources(mcp)
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

    # Add CORS middleware to handle OPTIONS preflight requests
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins (customize as needed)
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],  # Explicitly allow OPTIONS
        allow_headers=["*"],
    )

    # Add request logging middleware with MCP message inspection
    class RequestLoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Log all non-health-check requests with MCP details
            if request.url.path not in ["/health", "/healthz", "/readyz"]:
                mcp_details = await self._extract_mcp_details(request)
                logger.info(f"🌐 HTTP {request.method} {request.url.path}{mcp_details}")

            response = await call_next(request)

            # Log response status for non-health-checks
            if request.url.path not in ["/health", "/healthz", "/readyz"]:
                logger.info(f"   ← HTTP {response.status_code}")

            return response

        async def _extract_mcp_details(self, request: Request) -> str:
            """Extract MCP method and tool/resource details from request."""
            try:
                # Read body without consuming it for downstream
                body = await request.body()

                # Parse JSON-RPC message
                import json
                message = json.loads(body)

                method = message.get("method", "unknown")

                # Extract details based on method type
                if method == "tools/call":
                    params = message.get("params", {})
                    tool_name = params.get("name", "unknown")
                    return f" → tools/call({tool_name})"
                elif method == "resources/read":
                    params = message.get("params", {})
                    uri = params.get("uri", "unknown")
                    return f" → resources/read({uri})"
                elif method in ["tools/list", "resources/list", "prompts/list"]:
                    return f" → {method}"
                elif method == "initialize":
                    return f" → initialize"
                else:
                    return f" → {method}"

            except Exception:
                # If we can't parse, just return empty string
                return ""

    app.add_middleware(RequestLoggingMiddleware)

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
