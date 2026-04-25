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
import base64
import datetime
import hashlib
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

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
# FastMCP's auth loggers emit INFO lines that duplicate info our request
# middleware already logs (token rejection reason, 401 invalid_token). Keep
# WARNING+ so real problems still surface.
logging.getLogger("fastmcp.server.auth").setLevel(logging.WARNING)

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
SCAFFOLD RETRIEVAL CONTRACT (resource-first)
========================================================================

`generate_server_scaffold` returns a COMPACT manifest — no file bytes
are returned in tool output. Bulk byte transfer is a resource operation.

  Primary (bulk bytes):
      resources/read("scaffold://{project_id}/{path}")
      → Returns exact file bytes. Verify against artifacts[i].sha256.

  Primary (coordination metadata — no file contents):
      list_scaffold_artifact_metadata(project_id)
      read_scaffold_artifact_metadata(project_id, path)
      → role, customization_relevance, summary, symbols, notes.

  LAST-RESORT fallback (DO NOT use if resources/read is available):
      read_scaffold_artifact(project_id, path)
      → Full bytes in tool output — pulls every byte into model
        context. Reserved for tool-only proxy aggregators that drop
        resources entirely (e.g. OpenAI's codex_apps). If your client
        supports resources/read, using this tool is a bug.

HARD GATE — INVARIANT: every on-disk file must be byte-identical to the
stored artifact (verify via sha256). On ANY retrieval failure, STOP and
produce SCAFFOLD_RETRIEVAL_FAILURE.md (template in the
`failure_report_template` field of the scaffold response). Do NOT:
  - Reconstruct from memory
  - Render templates as a substitute (`render_template` is NOT a fallback)
  - Create placeholder files
  - Infer contents from filenames
  - Continue to customization with a partial scaffold
  - Produce SCAFFOLD_INVENTORY.md unless retrieval is 100% verified.

========================================================================
INTENDED AGENT WORKFLOW
========================================================================

1. result = generate_server_scaffold(server_name="My Server")
   → {project_id, file_count, artifacts, retrieval_contract, workflow}
2. For each entry in result["artifacts"]:
      bytes = resources/read(entry["uri"])
      write bytes to ./<entry["path"]>
      assert sha256(bytes) == entry["sha256"]
3. If all hashes match → create SCAFFOLD_INVENTORY.md locally.
   If any fail → STOP, write SCAFFOLD_RETRIEVAL_FAILURE.md, do not customize.
4. Inspect only files with customization_relevance in {"high","medium"};
   use read_scaffold_artifact_metadata for symbols/notes first.
5. Customize locally; chmod +x bin/*; python bin/configure-make.py;
   make build && make push && make helm-install.

For tool-only proxy clients (resources not forwarded by the proxy):
- Still call list_scaffold_artifact_metadata for coordination.
- Fall back to read_scaffold_artifact for byte transfer (accepts the
  context-bloat cost). The hash-verification gate is unchanged.

========================================================================
TOOLS
========================================================================

- generate_server_scaffold: Create project (returns compact manifest)
- list_scaffold_artifact_metadata: Compact metadata for all artifacts
- read_scaffold_artifact_metadata: Detailed metadata for one artifact
- read_scaffold_artifact: LAST-RESORT FALLBACK — full bytes in tool
    output. Do NOT use if resources/read is available.
- list_artifacts: Lightweight path + URI listing
- render_template: Render individual templates (NOT a scaffold substitute)
- list_templates / list_patterns / get_pattern: Discovery

========================================================================
RESOURCES
========================================================================

- scaffold://{project_id}/{path} — Concrete per-artifact resource
  (registered at generate_server_scaffold time; primary byte path)
- artifact://{project_id}/{path} — Alias for legacy clients
- template://... and pattern://... — Templates and pattern docs

NOTE: Utility scripts are available via the mcp-base CLI:
  pip install mcp-base
  mcp-base --help  # Shows: add-user, create-secrets, setup-oidc, setup-rbac
"""
)

# ============================================================================
# Register Resources and Tools from tools module
# ============================================================================

from mcp_base_tools import register_resources

register_resources(mcp)
register_tools(mcp)

# ============================================================================
# Auth diagnostic logging
# ============================================================================
#
# Decode-only inspection of incoming bearer JWTs for diagnosing client
# re-auth churn after pod restarts. We don't verify here — FastMCP's
# JWTVerifier still does that. This just surfaces enough of the token to
# distinguish three failure modes on a redeploy:
#   1. Token expired during idle window (benign, client should refresh).
#   2. Codex rotated to a brand-new token fingerprint (re-auth loop).
#   3. Same token, now rejected (JWKS rotation / audience mismatch).
#
# Never logs the token itself — only sub/jti/aud/iss, an expiry delta, a
# short sha256 fingerprint of the raw token, and the granted scopes.

def _inspect_bearer_token(auth_header: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return a compact summary of a Bearer JWT's claims, or None."""
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(None, 1)[1].strip()
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except Exception:
        return None
    scope = payload.get("scope") or payload.get("scp") or ""
    scopes = scope if isinstance(scope, list) else scope.split()
    exp = payload.get("exp")
    iat = payload.get("iat")
    now = int(time.time())
    exp_int = int(exp) if isinstance(exp, (int, float)) else None
    iat_int = int(iat) if isinstance(iat, (int, float)) else None
    lifespan = (exp_int - iat_int) if (exp_int is not None and iat_int is not None) else None
    age = (now - iat_int) if iat_int is not None else None
    return {
        "sub": payload.get("sub"),
        "jti": payload.get("jti"),
        "aud": payload.get("aud"),
        "iss": payload.get("iss"),
        "azp": payload.get("azp"),
        "sid": payload.get("sid") or payload.get("session_state"),
        "exp": exp_int,
        "exp_delta": (exp_int - now) if exp_int is not None else None,
        "iat": iat_int,
        "age": age,
        "lifespan": lifespan,
        "scopes": scopes,
        "token_fp": hashlib.sha256(token.encode()).hexdigest()[:10],
    }


def _humanize_seconds(s: int) -> str:
    s = abs(int(s))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    h, rem = divmod(s, 3600)
    return f"{h}h {rem // 60}m"


# Expiry age above which we assume the client's refresh flow is broken
# rather than "just barely stale." Keycloak's default access-token
# lifespan is 5 min; a well-behaved client refreshes long before 15 min.
_REFRESH_BROKEN_THRESHOLD_SEC = 15 * 60


def _format_exp_delta(delta: Optional[int]) -> str:
    if delta is None:
        return "?"
    if delta < 0:
        tail = "  ⚠️  refresh likely broken" if -delta > _REFRESH_BROKEN_THRESHOLD_SEC else ""
        return f"EXPIRED {_humanize_seconds(-delta)} ago{tail}"
    return f"valid for {_humanize_seconds(delta)}"


def _split_www_authenticate(header: str) -> list:
    """Split 'Bearer error="...", scope="...", resource_metadata="..."'
    into its individual key=value parts, tolerating commas inside quoted
    strings.
    """
    if not header:
        return []
    import re
    # Split on ", " only when it precedes a bare word= (i.e. a new field),
    # not inside a quoted value.
    return re.split(r',\s+(?=[A-Za-z_]+=)', header)


# ============================================================================
# Server Entry Point
# ============================================================================

def run_http_transport(port: int = 4208, host: str = "0.0.0.0"):
    """Run the MCP server with HTTP transport."""
    import uvicorn
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    from auth_fastmcp import create_auth_provider

    logger.info("Initializing FastMCP auth provider...")

    # Dispatch to the appropriate provider (auth0 / keycloak / oidc) based on
    # the auth_type key in oidc.yaml. See docs/cli-integration-contract.md §6.
    auth_proxy, auth_type, config_summary = create_auth_provider()

    logger.info("=" * 80)
    logger.info(f"FastMCP auth configuration (auth_type={auth_type}):")
    logger.info("=" * 80)
    for key, value in config_summary.items():
        logger.info(f"  {key}: {value}")
    logger.info("=" * 80)

    # Set auth on mcp instance
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
            skip = request.url.path in ["/health", "/healthz", "/readyz"]
            if not skip:
                mcp_details = await self._extract_mcp_details(request)
                lines = [f"🌐 HTTP {request.method} {request.url.path}{mcp_details}"]
                claims = _inspect_bearer_token(request.headers.get("authorization"))
                if claims is not None:
                    age_str = (
                        f"{_humanize_seconds(claims['age'])}"
                        if claims["age"] is not None else "?"
                    )
                    lifespan_str = (
                        f"{_humanize_seconds(claims['lifespan'])}"
                        if claims["lifespan"] is not None else "?"
                    )
                    lines += [
                        f"             sub       = {claims['sub'] or '(none)'}",
                        f"             azp       = {claims['azp'] or '(none)'}",
                        f"             sid       = {claims['sid'] or '(none)'}",
                        f"             jti       = {claims['jti'] or '(none)'}",
                        f"             token_fp  = {claims['token_fp']}",
                        f"             age       = {age_str}  (lifespan {lifespan_str})",
                        f"             exp       = {_format_exp_delta(claims['exp_delta'])}",
                        f"             scopes    = {' '.join(claims['scopes']) or '(none)'}",
                    ]
                logger.info("\n".join(lines))

            response = await call_next(request)

            if not skip:
                lines = [f"   ← HTTP {response.status_code}"]
                if response.status_code in (401, 403):
                    www_auth = response.headers.get("www-authenticate", "")
                    for part in _split_www_authenticate(www_auth):
                        lines.append(f"             {part}")
                logger.info("\n".join(lines))

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
    if auth_type == "keycloak":
        logger.info(f"  Auth: FastMCP KeycloakAuthProvider (Pattern B — IdP-served DCR)")
    else:
        logger.info(f"  Auth: FastMCP OAuth Proxy (Pattern A — issues MCP tokens)")
        logger.info(f"  OAuth Discovery: /.well-known/oauth-authorization-server")
        logger.info(f"  Client Registration: /register")
    logger.info("  Tools: MCP server construction tools")
    logger.info(
        "🟢 pod start: host=%s pid=%d start_ts=%sZ auth_type=%s",
        socket.gethostname(),
        os.getpid(),
        datetime.datetime.utcnow().isoformat(timespec="seconds"),
        auth_type,
    )
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
