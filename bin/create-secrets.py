#!/usr/bin/env python3
"""
DEPRECATED — superseded by `mcp-base create-secrets`.

Secret creation now lives in the mcp-base-cli package (pip install mcp-base).
It reads oidc-config.json (not auth0-config.json), understands Pattern A vs
Pattern B, and is a no-op for Keycloak deployments where no Kubernetes
credentials secret is required.

See docs/cli-integration-contract.md §5 for the authoritative secret schema.
"""

import sys

MESSAGE = """\
bin/create-secrets.py has been removed.

Use the mcp-base CLI instead:

    pip install mcp-base
    mcp-base create-secrets --namespace <ns> --release-name <release>

For Keycloak (Pattern B) deployments, this command is a no-op — Keycloak's
native DCR means no Kubernetes client-credentials secret is required.
"""


def main() -> int:
    sys.stderr.write(MESSAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main())
