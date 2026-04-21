# Authentication Pattern

This document describes the Auth0 / Keycloak / generic-OIDC authentication
patterns for remote MCP servers.

## Overview

Remote MCP servers use OAuth 2.0 / OIDC authentication. Pick one of three
providers at scaffold time via the `auth_type` parameter:

| `auth_type` | FastMCP provider | Best for |
|---|---|---|
| `auth0` (default) | `fastmcp.server.auth.providers.auth0.Auth0Provider` | Auth0; OAuth proxy that issues MCP tokens and persists sessions in Redis |
| `keycloak` | `fastmcp.server.auth.providers.keycloak.KeycloakAuthProvider` | Keycloak 26.6.0+; uses native Dynamic Client Registration (no client_secret/Redis) |
| `oidc` | Custom `OIDCAuthProvider` middleware (`auth_oidc.py`) | Dex, Okta, Azure AD and other generic OIDC IdPs |

The generic flow for all three:

1. Client initiates OAuth flow with the IdP
2. User authenticates via browser
3. IdP issues a JWT access token
4. Client includes token in the `Authorization` header
5. Server validates the JWT and extracts user info

**`auth0` vs `keycloak`:** the Auth0 path runs a full FastMCP `OIDCProxy`
that issues its own MCP-signed JWTs and encrypts Auth0 tokens in Redis.
The Keycloak path uses `RemoteAuthProvider` — Keycloak handles DCR natively
and tokens are verified directly against its JWKS, so no `client_id`/
`client_secret`, JWT signing key, or Redis storage is required.

## DCR model per provider

MCP clients register themselves at runtime via OAuth 2.1 Dynamic Client
Registration (DCR, RFC 7591). Who actually serves that DCR endpoint differs
by provider, and FastMCP 3 uses two architecturally distinct patterns.

### Pattern A — Proxy (FastMCP serves DCR locally)

Classes: `OAuthProxy` → `OIDCProxy` → `Auth0Provider`.

FastMCP exposes its own DCR-compliant endpoint to MCP clients and *translates*
each registration into a call against the upstream IdP using a single
pre-registered `client_id`/`client_secret`. FastMCP issues its own signed
MCP tokens and persists upstream IdP tokens encrypted in Redis.

This pattern is used for IdPs that either don't support DCR at all, or whose
DCR flow isn't MCP-compatible. Even Auth0 — which does support DCR — is
wired through this proxy in FastMCP 3, so Auth0 deployments still require
`client_id`/`client_secret`, a JWT signing key, and Redis.

### Pattern B — Remote (IdP serves DCR directly)

Classes: `RemoteAuthProvider` → `KeycloakAuthProvider`.

FastMCP does **not** run a DCR endpoint. It only publishes RFC 9728
Protected Resource metadata that points MCP clients at the IdP's own
authorization server and DCR endpoint. Tokens are verified directly against
the IdP's JWKS. No `client_id`/`client_secret` sits in FastMCP, no MCP token
is minted, no Redis is needed.

This pattern only works when the IdP runs a DCR endpoint that MCP clients
can actually use. For Keycloak that means **≥ 26.6.0** (keycloak/keycloak#45309).
Earlier Keycloak versions expose a DCR endpoint but produce clients that are
incompatible with MCP flows — `KeycloakAuthProvider` will not work against
them.

### What changed from FastMCP 2 → 3

FastMCP 2 only had Pattern A: `OAuthProxy` ran local DCR for every IdP.
FastMCP 3.2.4 keeps that path unchanged (Auth0Provider still extends
`OIDCProxy`) and adds `RemoteAuthProvider` as an alternate pattern. The new
`KeycloakAuthProvider` is the first first-party user of Pattern B. Nothing
else in the provider set moved — Dex, Okta, Azure AD, and other generic
OIDC IdPs still need Pattern A (either via a FastMCP proxy provider or our
own `auth_oidc.py` middleware).

### Selection matrix

| IdP | Pattern | FastMCP class | Needs local `client_id`/`secret` | Needs Redis | Needs JWT signing key | Hard IdP version pin |
|---|---|---|---|---|---|---|
| Auth0 | A (proxy) | `Auth0Provider` | yes | yes | yes | — |
| Keycloak ≥ 26.6.0 | B (remote) | `KeycloakAuthProvider` | no | no | no | Keycloak ≥ 26.6.0 |
| Keycloak < 26.6.0 | A (proxy) via `oidc` | `OIDCAuthProvider` (ours) | yes | yes* | yes* | — |
| Dex / Okta / Azure AD / generic | A (proxy) via `oidc` | `OIDCAuthProvider` (ours) | yes | yes* | yes* | — |

\* Redis / JWT signing key are required by our Pattern A implementation
because it mints and persists MCP-side tokens; a different Pattern A
implementation could trade these off.

### Load-bearing assumption

The Keycloak path trades FastMCP-side complexity (client creds, token
re-issuance, Redis) for a hard Keycloak version requirement. If an operator
is pinned to a Keycloak release older than 26.6.0, `auth_type="keycloak"`
is not a valid choice and the scaffold must fall back to `auth_type="oidc"`.

## FastMCP Auth0Provider Configuration

```python
from fastmcp import FastMCP
from fastmcp.server.auth import Auth0OAuthProvider

# Environment variables for Auth0 configuration
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN")
AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE")

# Create Auth0 provider
auth = Auth0OAuthProvider(
    domain=AUTH0_DOMAIN,
    client_id=AUTH0_CLIENT_ID,
    client_secret=AUTH0_CLIENT_SECRET,
    audience=AUTH0_AUDIENCE
)

# Create MCP server with auth
mcp = FastMCP(
    "server-name",
    auth=auth
)
```

## Redis Session Storage

OAuth sessions require persistent storage. Use Redis for session management:

```python
import redis

# Redis configuration from environment
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Configure FastMCP to use Redis
mcp = FastMCP(
    "server-name",
    auth=auth,
    session_store_url=REDIS_URL
)
```

## Keycloak (`auth_type="keycloak"`)

Requires **fastmcp >= 3.2.4** and **Keycloak >= 26.6.0** (needs the DCR/MCP
fix from keycloak/keycloak#45309). No `client_id`/`client_secret`, JWT
signing key, or Redis is required — clients register dynamically and tokens
are verified directly against Keycloak's JWKS endpoint.

```python
from fastmcp import FastMCP
from fastmcp.server.auth.providers.keycloak import KeycloakAuthProvider

auth = KeycloakAuthProvider(
    realm_url="https://keycloak.example.com/realms/myrealm",
    base_url="https://my-mcp-server.example.com",
    audience="https://my-mcp-server.example.com/mcp",  # optional but recommended
    required_scopes=["openid"],                         # default
)

mcp = FastMCP("server-name", auth=auth)
```

Typical `oidc.yaml` for a Keycloak-backed deployment:

```yaml
realm_url: https://keycloak.example.com/realms/myrealm
public_url: https://mcp-server.example.com
audience: https://mcp-server.example.com/mcp
required_scopes: [openid]
```

Environment-variable equivalents: `KEYCLOAK_REALM_URL` (or `OIDC_ISSUER`),
`PUBLIC_URL`, `OIDC_AUDIENCE`.

## Standard OIDC Provider (`auth_type="oidc"`)

For other OIDC IdPs (Dex, Okta, Azure AD). Uses the generated `auth_oidc.py`
middleware, which validates JWTs against the discovered JWKS and optionally
proxies DCR to an upstream endpoint:

```python
from auth_oidc import OIDCAuthProvider

# Environment variables
OIDC_ISSUER = os.environ.get("OIDC_ISSUER")  # e.g., https://dex.example.com
OIDC_AUDIENCE = os.environ.get("OIDC_AUDIENCE")

auth_provider = OIDCAuthProvider()  # reads config from file/env
```

## JWT Token Structure

Expected JWT claims from Auth0:

```json
{
  "iss": "https://tenant.auth0.com/",
  "sub": "auth0|user123",
  "aud": "mcp-api",
  "iat": 1699999999,
  "exp": 1700003599,
  "azp": "client-id",
  "scope": "openid profile email",
  "preferred_username": "user@example.com"
}
```

## User ID Generation

Generate RFC 1123 compatible user IDs from JWT claims:

```python
import hashlib
import re

def generate_user_id(preferred_username: str, issuer: str) -> str:
    """
    Generate RFC 1123 compatible user ID from JWT claims.

    Format: {sanitized_username}-{hash}
    - Username sanitized to lowercase alphanumeric + hyphens
    - Hash provides uniqueness across issuers
    """
    # Sanitize username
    sanitized = re.sub(r'[^a-z0-9-]', '-', preferred_username.lower())
    sanitized = re.sub(r'-+', '-', sanitized).strip('-')[:20]

    # Create hash from username + issuer
    combined = f"{preferred_username}:{issuer}"
    hash_suffix = hashlib.sha256(combined.encode()).hexdigest()[:8]

    return f"{sanitized}-{hash_suffix}"
```

## Extracting User Info from Request

```python
import base64
import json

def extract_user_info_from_request(request) -> dict:
    """Extract user info from JWT in Authorization header."""
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]

    # Decode JWT payload (middle part)
    parts = token.split(".")
    if len(parts) != 3:
        return None

    # Add padding and decode
    payload = parts[1]
    payload += "=" * (4 - len(payload) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload))

    # Extract claims
    preferred_username = (
        decoded.get("preferred_username") or
        decoded.get("email") or
        decoded.get("name") or
        decoded.get("sub", "unknown")
    )
    issuer = decoded.get("iss", "unknown")

    return {
        "user_id": generate_user_id(preferred_username, issuer),
        "preferred_username": preferred_username,
        "issuer": issuer
    }
```

## Auth0 Setup Script Pattern

Automate Auth0 tenant configuration:

```python
#!/usr/bin/env python3
"""Setup Auth0 tenant for MCP server."""

import requests

class Auth0Setup:
    def __init__(self, domain: str, mgmt_token: str):
        self.domain = domain
        self.mgmt_token = mgmt_token
        self.base_url = f"https://{domain}/api/v2"

    def create_api(self, identifier: str, name: str):
        """Create Auth0 API (Resource Server)."""
        return requests.post(
            f"{self.base_url}/resource-servers",
            headers={"Authorization": f"Bearer {self.mgmt_token}"},
            json={
                "identifier": identifier,
                "name": name,
                "signing_alg": "RS256",
                "token_lifetime": 86400,
                "scopes": [
                    {"value": "openid", "description": "OpenID"},
                    {"value": "profile", "description": "Profile"},
                    {"value": "email", "description": "Email"}
                ]
            }
        )

    def create_application(self, name: str, callback_urls: list):
        """Create Auth0 Application (Client)."""
        return requests.post(
            f"{self.base_url}/clients",
            headers={"Authorization": f"Bearer {self.mgmt_token}"},
            json={
                "name": name,
                "app_type": "regular_web",
                "callbacks": callback_urls,
                "grant_types": [
                    "authorization_code",
                    "refresh_token"
                ],
                "token_endpoint_auth_method": "client_secret_post"
            }
        )
```

## Kubernetes Secret Structure

Store Auth0 credentials in Kubernetes secrets:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mcp-auth0-credentials
type: Opaque
stringData:
  server-client-id: "your-client-id"
  server-client-secret: "your-client-secret"
  auth0-domain: "tenant.auth0.com"
---
apiVersion: v1
kind: Secret
metadata:
  name: mcp-jwt-signing-key
type: Opaque
stringData:
  jwt-signing-key: "generated-256-bit-hex-key"
  storage-encryption-key: "fernet-key-for-oauth-tokens"
```

## Environment Variables

Required environment variables for authentication:

| Variable | Description | Example |
|----------|-------------|---------|
| `AUTH0_DOMAIN` | Auth0 tenant domain | `tenant.auth0.com` |
| `AUTH0_CLIENT_ID` | OAuth client ID | `abc123...` |
| `AUTH0_CLIENT_SECRET` | OAuth client secret | `secret...` |
| `AUTH0_AUDIENCE` | API identifier | `https://mcp-api` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379` |
| `JWT_SIGNING_KEY` | Key for MCP tokens | `hex-string` |

## Best Practices

1. **Never hardcode credentials** - Always use environment variables or secrets
2. **Use short-lived tokens** - 15-60 minutes recommended
3. **Validate all claims** - Issuer, audience, expiration
4. **Log authentication events** - For audit trails
5. **Use Redis for sessions** - Required for OAuth token storage
6. **Rotate secrets regularly** - Automate with Kubernetes CronJobs
