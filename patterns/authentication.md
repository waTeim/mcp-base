# Authentication Pattern

This document describes the Auth0/OIDC authentication pattern for remote MCP servers.

## Overview

Remote MCP servers use OAuth 2.0 / OIDC authentication via FastMCP's Auth0Provider. The authentication flow:

1. Client initiates OAuth flow with Auth0
2. User authenticates via browser
3. Auth0 issues JWT access token
4. Client includes token in Authorization header
5. Server validates JWT and extracts user info

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

## Standard OIDC Provider (Alternative)

For standard OIDC validation without OAuth proxy:

```python
from auth_oidc import create_oidc_provider

# Environment variables
OIDC_ISSUER = os.environ.get("OIDC_ISSUER")  # e.g., https://tenant.auth0.com/
OIDC_AUDIENCE = os.environ.get("OIDC_AUDIENCE")

# Create OIDC provider
oidc_provider = create_oidc_provider(
    issuer=OIDC_ISSUER,
    audience=OIDC_AUDIENCE
)
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
