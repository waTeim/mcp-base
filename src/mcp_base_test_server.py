#!/usr/bin/env python3
"""
MCP Base MCP Test Server (OIDC Auth)

Test endpoint for the MCP Base MCP server using standard OIDC authentication.
This server accepts Auth0 JWT tokens directly (no MCP token issuance).

This is deployed as a sidecar container alongside the main FastMCP OAuth server,
allowing both authentication methods to coexist:
- Main server (port 8000): FastMCP OAuth proxy issuing MCP tokens
- Test server (port 8001): Standard OIDC accepting Auth0 JWT tokens

Both servers share the same tool implementations from mcp_base_tools.py.
"""

import argparse
import logging
import sys
import os
import warnings

# Suppress deprecation warnings from dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, module="urllib3")
warnings.filterwarnings("ignore", message=".*HTTPResponse.getheaders.*")

from fastmcp import FastMCP, Context
import uvicorn
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import json as json_module

# Import shared tools and resources registration
from mcp_base_tools import register_tools, register_resources

# Import OIDC auth
from auth_oidc import OIDCAuthProvider, OIDCAuthMiddleware

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
# FastMCP Server Initialization
# ============================================================================

mcp = FastMCP(
    "mcp-base-test",
    instructions="""
MCP Base MCP Test Server (OIDC Auth).

This is the test server endpoint that accepts Auth0 JWT tokens directly.
Use this for testing with standard OIDC authentication.
"""
)

# ============================================================================
# Register Resources and Tools
# ============================================================================

logger.info("Registering resources...")
register_resources(mcp)

# Debug: Log registered resources
try:
    if hasattr(mcp, '_resource_manager') and hasattr(mcp._resource_manager, '_resources'):
        resource_count = len(mcp._resource_manager._resources)
        logger.info(f"   Registered {resource_count} resources")
        for uri in list(mcp._resource_manager._resources.keys())[:5]:
            logger.info(f"      - {uri}")
        if resource_count > 5:
            logger.info(f"      ... and {resource_count - 5} more")
    else:
        logger.warning("   Cannot access resource manager")
except Exception as e:
    logger.warning(f"   Error inspecting resources: {e}")

logger.info("Registering tools...")
register_tools(mcp)

logger.info("✅ Resources and tools registered with test MCP server")

# ============================================================================
# MCP Protocol Logging Middleware
# ============================================================================

def add_mcp_logging():
    """Add detailed logging for MCP protocol operations."""

    # Wrap at the resource_manager level
    original_get_resources = mcp._resource_manager.get_resources
    async def logged_get_resources():
        logger.info("📋 MCP: get_resources called on resource_manager")
        logger.info(f"   Internal state: {len(mcp._resource_manager._resources)} resources in _resources dict")
        result = await original_get_resources()
        logger.info(f"   → Type of result: {type(result)}")

        # Get actual resource objects (dict values, not keys!)
        if isinstance(result, dict):
            result_list = list(result.values())
            logger.info(f"   → Dict with {len(result_list)} resource objects")
            for i, r in enumerate(result_list[:3]):
                logger.info(f"      [{i}] Type: {type(r)}")
                if hasattr(r, 'uri'):
                    logger.info(f"           URI: {r.uri}")
                if hasattr(r, 'name'):
                    logger.info(f"           Name: {r.name}")
            if len(result_list) > 3:
                logger.info(f"      ... and {len(result_list) - 3} more")
        else:
            logger.info(f"   → Returning {len(result)} resources (not a dict)")

        return result
    mcp._resource_manager.get_resources = logged_get_resources

    # Also wrap the FastMCP _list_resources handler
    original_list_resources_handler = mcp._list_resources
    async def logged_list_resources_handler(context):
        logger.info("🔍 MCP: _list_resources (middleware) called")
        result = await original_list_resources_handler(context)
        logger.info(f"   → Result type: {type(result)}")
        logger.info(f"   → Result length: {len(result)}")
        return result
    mcp._list_resources = logged_list_resources_handler

    # Wrap the MCP protocol handler that returns MCPResource objects
    original_list_resources_mcp = mcp._list_resources_mcp
    async def logged_list_resources_mcp():
        logger.info("🔍 MCP: _list_resources_mcp (protocol) called")
        result = await original_list_resources_mcp()
        logger.info(f"   → MCP protocol result type: {type(result)}")
        logger.info(f"   → MCP protocol result length: {len(result)}")
        if len(result) > 0:
            logger.info(f"   → First item type: {type(result[0])}")
            logger.info(f"   → First item: {result[0]}")
        return result
    mcp._list_resources_mcp = logged_list_resources_mcp

add_mcp_logging()
logger.info("✅ MCP protocol logging enabled")

# ============================================================================
# Health Check Endpoints
# ============================================================================

async def liveness_check(request):
    """Kubernetes liveness probe endpoint."""
    return JSONResponse({"status": "alive"})


async def readiness_check(request):
    """Kubernetes readiness probe endpoint."""
    return JSONResponse({"status": "ready"})


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the test server."""
    parser = argparse.ArgumentParser(
        description="MCP Base MCP Test Server (OIDC Auth)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("TEST_PORT", "4209")),
        help="Port to listen on (default: 4209)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("MCP Base MCP Test Server (OIDC Auth)")
    logger.info("=" * 70)
    logger.info(f"Listening on: {args.host}:{args.port}")
    logger.info(f"Endpoint: /test")
    logger.info(f"Auth: Standard OIDC (Auth0 JWT tokens)")
    logger.info("=" * 70)

    # Create OIDC auth provider
    logger.info("Initializing OIDC authentication...")
    oidc_provider = OIDCAuthProvider()
    logger.info(f"   Issuer: {oidc_provider.issuer}")
    logger.info(f"   Audience: {oidc_provider.audience}")

    # Create FastMCP HTTP app
    logger.info("Creating HTTP app at path /test...")
    app = mcp.http_app(path="/test")
    logger.info(f"   HTTP app created: {type(app)}")

    # Add simple request logging middleware (no body reading to preserve streaming)
    class RequestLoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Log all non-health-check requests
            if request.url.path not in ["/healthz", "/readyz"]:
                logger.info(f"🌐 HTTP {request.method} {request.url.path}")

            response = await call_next(request)

            # Log response status for non-health-checks
            if request.url.path not in ["/healthz", "/readyz"]:
                logger.info(f"   ← HTTP {response.status_code}")

            return response

    logger.info("Adding request logging middleware...")
    app.add_middleware(RequestLoggingMiddleware)

    # Add OIDC middleware
    logger.info("Adding OIDC authentication middleware...")
    app.add_middleware(
        OIDCAuthMiddleware,
        auth_provider=oidc_provider,
        exclude_paths=["/healthz", "/readyz"]
    )

    # Add health check routes
    app.add_route("/healthz", liveness_check)
    app.add_route("/readyz", readiness_check)

    logger.info("✅ Test server ready")
    logger.info("")
    logger.info("To test with Auth0 JWT token:")
    logger.info("  1. Get token: ./test/get-user-token.py")
    logger.info("  2. Test: ./test/test-mcp.py --transport http \\")
    logger.info(f"           --url http://localhost:{args.port}/test \\")
    logger.info("           --token-file /tmp/user-token.txt")
    logger.info("")

    # Add health check filter to uvicorn access logger
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

    # Run server
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        ws="none"
    )


if __name__ == "__main__":
    main()