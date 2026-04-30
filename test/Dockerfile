# MCP Base Test Server - Dockerfile
#
# Thin layer over the main MCP Base server image. The test server reuses the
# exact same Python environment, source tree, templates, and patterns as the
# production image; the only differences are:
#   - CMD launches mcp_base_test_server.py instead of mcp_base_server.py
#   - --no-auth is enabled by default so authentication is disabled
#   - --identity supplies the mock sub / iss claims that downstream tools
#     (mcp_context, user_hash) require
#
# Because the test surface has no OIDC, the deployment chart MUST keep this
# container reachable only from inside the cluster (ClusterIP) or via
# `kubectl port-forward` — never via Ingress.

# Default is a placeholder so `docker build` without --build-arg still parses
# cleanly (silences BuildKit's InvalidDefaultArgInFrom warning). The Makefile
# always overrides BASE_IMAGE with the freshly-built main image tag.
ARG BASE_IMAGE=mcp-base-server:latest
FROM ${BASE_IMAGE}

LABEL component="test-sidecar"
LABEL description="MCP Test Server for MCP Base (no-auth, in-cluster only)"

EXPOSE 4201

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:4201/healthz || exit 1

CMD ["python", "mcp_base_test_server.py","--no-auth","--identity","test-user","--host","0.0.0.0","--port","4201"]
