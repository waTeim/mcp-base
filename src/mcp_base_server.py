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
5. **Edit `mcp-project.yaml` first.** It is the canonical source of truth
   for: project name, chart name, ports.main / ports.test, build
   registry/imageName/testImageName/tag/platform/containerTool, and
   deployment helmRelease/namespace/serviceType/testSidecarEnabled.
   Every other build/deployment artifact (Makefile vars, image tags,
   helm release name, port arguments) ultimately derives from this file.
6. Run `python bin/sync-config.py` to regenerate `make.env` from the
   project config. Re-run after any subsequent edits to `mcp-project.yaml`.
7. Edit the release values overlay at the repo root,
   `<helmRelease>.yaml` (e.g. `my-server.yaml`). This is a deployment
   artifact — chart defaults live in `chart/values.yaml`; per-release
   overrides (image.repository, ingress host, OIDC issuer/audience, etc.)
   live in this file. The Makefile passes it via `helm -f`.
8. Customize src/<server>_tools.py — add @mcp.tool / @mcp.resource /
   @mcp.prompt implementations.
9. **Write tests for every tool you add.** This is not optional. The
   scaffold ships test/plugins/test_example.py as a richly-commented
   starter; copy it to test/plugins/test_<your_tool>.py per new tool,
   and assert BOTH a happy path AND at least one error path. See
   pattern://testing for the contract and worked examples. Run
   `make dev-coverage` and confirm the lines you added show up as
   covered before declaring the tool done.
10. chmod +x bin/*; make build && make push && make helm-install.
    NOTE: `helm-install` does NOT pass `--create-namespace` (assumes
    cluster-admin) or `--wait` (blocks on crashing sidecars). Pre-create
    the namespace if needed and check readiness with `make k8s-pods`.
11. `make test-cluster` exercises the in-cluster test sidecar
    (auto-managed kubectl port-forward, no auth setup needed). Use
    `make test-cluster-prod --token-file=/tmp/user-token.txt` against
    the production endpoint.

For tool-only proxy clients (resources not forwarded by the proxy):
- Still call list_scaffold_artifact_metadata for coordination.
- Fall back to read_scaffold_artifact for byte transfer (accepts the
  context-bloat cost). The hash-verification gate is unchanged.

========================================================================
CANONICAL PROJECT CONFIG (mcp-project.yaml)
========================================================================

The scaffold ships `mcp-project.yaml` at the repo root as the single
source of truth for build + deployment defaults:

  project:    name, chartName
  ports:      main (default 4200), test (default 4201)
  build:      registry, imageName, testImageName, tag, platform,
              containerTool
  deployment: helmRelease, namespace, serviceType, testSidecarEnabled

Downstream artifacts are derived from this file:

  bin/sync-config.py   reads mcp-project.yaml → writes make.env
  Makefile             includes make.env (REGISTRY, IMAGE_NAME, TAG,
                       HELM_RELEASE, HELM_NAMESPACE, HELM_SERVICE,
                       HELM_VALUES_FILE, MCP_PORT, MCP_TEST_PORT)
  test/test-mcp.py     reads ports.main / ports.test for --url and
                       --local-port / --remote-port defaults
  Dockerfile           copies mcp-project.yaml into /app for runtime
                       port reads
  chart/values.yaml    chart defaults (matches ports.* by default)
  <helmRelease>.yaml   release values overlay at repo root, NOT under
                       chart/. Treated as a deployment artifact and
                       passed to helm via -f $(HELM_VALUES_FILE).

Workflow:
  - Editing the project config means re-running sync-config.py.
  - Never edit make.env by hand — regenerate it.
  - The Makefile defaults still work without sync-config.py for the
    initial scaffold, but stay aligned with mcp-project.yaml.

The chart's testSidecar.image.repository defaults to "" — the chart
template derives a test image name by replacing the trailing
"-server" with "-test-server" against image.repository. The
sidecar MUST run the test image (the production image deliberately
does not contain the test_server.py entrypoint).

========================================================================
TESTING (REQUIRED, NOT OPTIONAL)
========================================================================

Every @mcp.tool you add must have a corresponding plugin under
test/plugins/test_<your_tool>.py. The harness is designed to make
this mechanical:

  - test/plugins/test_example.py is the starter — copy it per tool.
  - test/plugins/__init__.py defines TestPlugin / TestResult /
    TestContext. Plugins receive a live MCP session and (optionally) a
    TestContext for cross-plugin state via `ctx.shared`.
  - `make dev-coverage` spawns the test server under coverage.py,
    runs the plugin suite, and prints line/branch coverage. Use it
    to confirm your new tool's lines are actually exercised.
  - `make test-cluster` runs the same suite against the in-cluster
    test sidecar via auto-managed `kubectl port-forward`.

Read pattern://testing for the full contract: signatures, ordering
via depends_on/run_after, ctx.shared conventions, the operational-
error helper, and gotchas (AnyUrl conversion, contents vs content,
preferring "Error: ..." returns over raises).

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

def run_http_transport(port: int = 4200, host: str = "0.0.0.0"):
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
  python mcp_base_server.py --port 4200

  # Run with custom host
  python mcp_base_server.py --host 127.0.0.1 --port 3000

Environment Variables:
  PORT        Default HTTP port (default: 4200)
  HOST        Default host binding (default: 0.0.0.0)
        """
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 4200)),
        help="HTTP server port (default: 4200)"
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
