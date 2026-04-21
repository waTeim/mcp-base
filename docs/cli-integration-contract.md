# mcp-base ↔ mcp-base-cli Integration Contract

Audience: an agent modifying **mcp-base-cli** so that its `setup-oidc`,
`create-secrets`, and related commands produce artifacts that the
**mcp-base** Helm chart and scaffolded MCP servers consume correctly.

This document is the single source of truth for filenames, schemas, secret
layouts, and mount paths. If the CLI and chart disagree, this document
decides who is wrong.

---

## 1. Background — why two shapes

mcp-base supports three `auth_type` values (`auth0`, `keycloak`, `oidc`)
which resolve to **two architecturally distinct authentication patterns**
(see `patterns/authentication.md` → "DCR model per provider"):

| `auth_type` | DCR pattern | FastMCP class | Needs local client secret | Needs Redis | Needs JWT signing key |
|---|---|---|---|---|---|
| `auth0` | **A — Proxy** | `Auth0Provider` | yes | yes | yes |
| `oidc` (Dex/Okta/Azure AD/…) | **A — Proxy** (ours) | `OIDCAuthProvider` | yes | yes | yes |
| `keycloak` (≥ 26.6.0) | **B — Remote** | `KeycloakAuthProvider` | **no** | **no** | **no** |

Every CLI-produced artifact must branch on pattern, not on IdP name. When
this doc says "Pattern A" or "Pattern B" it refers to the table above.

---

## 2. Artifacts the CLI owns

The CLI produces three things; the chart consumes all three.

| Artifact | Produced by | Consumed by | Purpose |
|---|---|---|---|
| `oidc-config.json` | `mcp-base setup-oidc` | future CLI runs; humans | Persisted config so later CLI invocations can regenerate values / rotate secrets without prompts |
| `oidc-values.yaml` | `mcp-base setup-oidc` | `helm install -f oidc-values.yaml` | Helm values overlay for the mcp-base chart |
| Kubernetes `Secret` objects | `mcp-base create-secrets` | Chart `Deployment` / `ConfigMap` | Hold client secret and (Pattern A only) JWT signing + storage encryption keys |

The CLI must **not** produce shell scripts, Dockerfiles, or source code.
Those are owned by mcp-base's scaffold generator.

---

## 3. Authoritative schema — `oidc-config.json`

This file is CLI-internal state. It is **not** read by the server or the
chart directly. Shape:

```jsonc
{
  // Required in all patterns
  "provider": "auth0" | "keycloak" | "dex" | "okta" | "generic",
  "pattern": "proxy" | "remote",          // NEW — derived from provider
  "issuer": "https://…",
  "audience": "https://…/mcp",

  // Pattern A only. Omit entirely for Pattern B.
  "server_client": {
    "client_id":     "…",
    "client_secret": "…"
  },

  // Optional / always present if validation succeeded
  "authorization_endpoint": "https://…",
  "token_endpoint":         "https://…",
  "jwks_uri":               "https://…"
}
```

Rules:

- `provider: "keycloak"` ⇒ `pattern: "remote"` and `server_client` MUST be
  omitted. The current CLI writes `server_client` here for Keycloak — that
  is wrong and should be dropped (see §8).
- Any other provider ⇒ `pattern: "proxy"` and `server_client` MUST be
  present.
- `issuer` for Keycloak is a realm URL
  (`https://host/realms/<realm>`), which is what FastMCP's
  `KeycloakAuthProvider` calls `realm_url`. The CLI may continue calling it
  `issuer` in the JSON for consistency; the chart does the rename.

---

## 4. Authoritative schema — `oidc-values.yaml`

This is a Helm values overlay. It must match the mcp-base chart's
`values.yaml` shape exactly. Chart keys that matter here:

```yaml
# Pattern-agnostic
oidc:
  authType: "auth0" | "keycloak" | "oidc"   # NEW — required, drives chart branches
  issuer:   "https://…"
  audience: "https://…/mcp"
  publicUrl: "https://mcp-server.example.com"   # optional; else derived from ingress

# Pattern A only
oidc:
  clientId: "…"
  # clientSecret is NEVER in values — always from Secret (see §5)

# Pattern B only — nothing extra; required_scopes defaults to ["openid"]
oidc:
  requiredScopes: ["openid"]                # optional override

# Redis subchart — MUST be disabled for Pattern B
redis:
  enabled: true    # Pattern A
  # enabled: false # Pattern B

# JWT secret — MUST be skipped for Pattern B
jwt:
  enabled: true    # Pattern A (NEW flag; see §8)
  # enabled: false # Pattern B
```

Rules for the CLI:

- Always emit `oidc.authType`. It is the single switch the chart uses to
  enable/disable Pattern-A-only resources.
- For Pattern B, emit `redis.enabled: false` and `jwt.enabled: false`
  explicitly — don't rely on chart defaults.
- Never emit a raw `clientSecret` into values. The chart reads it from a
  mounted file in the Secret.

Current CLI output uses `oidc.clientId` (camelCase) — keep that. Existing
chart code uses camelCase under `oidc.*` too, so this is aligned.

---

## 5. Authoritative schema — Kubernetes `Secret`s

`create-secrets` must produce one or two Secrets, named deterministically
from the release name.

### 5.1 `<release>-oidc-credentials` (Pattern A only)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: <release>-oidc-credentials
type: Opaque
stringData:
  server-client-id:     "…"
  server-client-secret: "…"
```

- **Name change**: current chart hardcodes `<release>-auth0-credentials`.
  Rename to `<release>-oidc-credentials` (CLI already uses this name;
  chart is wrong — see §8).
- Mount path: `/etc/mcp/secrets/oidc/` (rename from
  `/etc/mcp/secrets/auth0/`).
- File read by server: `/etc/mcp/secrets/oidc/server-client-secret`.

### 5.2 `<release>-jwt-signing-key` (Pattern A only)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: <release>-jwt-signing-key
type: Opaque
stringData:
  jwt-signing-key:        "<hex-bytes>"
  storage-encryption-key: "<fernet-key>"
```

Mount path: `/etc/mcp/secrets/`. Files:
`/etc/mcp/secrets/jwt-signing-key`,
`/etc/mcp/secrets/storage-encryption-key`.

### 5.3 Pattern B — no Secrets required

Keycloak ≥ 26.6.0 clients register via DCR; tokens are verified against
JWKS. The CLI `create-secrets` command must be a no-op (print a notice and
exit 0) when `oidc-config.json` has `pattern: "remote"`.

---

## 6. ConfigMap and mount-path contract

The chart renders `/etc/mcp/oidc.yaml` from Helm values into a ConfigMap.
That file is what the server reads at startup. Its shape differs by
pattern.

### 6.1 Pattern A `oidc.yaml`

```yaml
auth_type: auth0      # or "oidc"
issuer: https://…
audience: https://…/mcp
client_id: …
client_secret_file: /etc/mcp/secrets/oidc/server-client-secret
jwt_signing_key_file: /etc/mcp/secrets/jwt-signing-key
storage_encryption_key_file: /etc/mcp/secrets/storage-encryption-key
public_url: https://mcp-server.example.com
redis:
  host: <release>-redis
  port: 6379
  db: 0
```

### 6.2 Pattern B `oidc.yaml`

```yaml
auth_type: keycloak
realm_url: https://keycloak.example.com/realms/myrealm
audience: https://mcp-server.example.com/mcp
public_url: https://mcp-server.example.com
required_scopes: [openid]
```

Note the **rename**: Pattern B uses `realm_url`, not `issuer`, to match
FastMCP's `KeycloakAuthProvider` parameter name. The ConfigMap template
must emit the right key.

### 6.3 Mount paths (single source of truth)

| Path in container | Source | Patterns |
|---|---|---|
| `/etc/mcp/oidc.yaml` | ConfigMap `<release>-oidc-config`, key `oidc.yaml` | A + B |
| `/etc/mcp/secrets/oidc/server-client-secret` | Secret `<release>-oidc-credentials` | A only |
| `/etc/mcp/secrets/jwt-signing-key` | Secret `<release>-jwt-signing-key` | A only |
| `/etc/mcp/secrets/storage-encryption-key` | Secret `<release>-jwt-signing-key` | A only |

The scaffolded server reads `oidc.yaml` from `/etc/mcp/oidc.yaml`. Do not
introduce an `/etc/mcp/oidc/oidc.yaml` subdirectory — the chart mounts
flat.

---

## 7. Current mismatches (snapshot)

Enumerated so the CLI agent and chart agent can divide work. Observed by
running `mcp-base setup-oidc --provider keycloak` against this repo and
comparing to the chart:

| # | Mismatch | Owner to fix |
|---|---|---|
| M1 | CLI writes `server_client` into `oidc-config.json` for Keycloak | CLI — drop it for Pattern B |
| M2 | CLI doesn't emit `oidc.authType` into `oidc-values.yaml` | CLI — always emit |
| M3 | CLI doesn't emit `redis.enabled: false` / `jwt.enabled: false` for Pattern B | CLI — emit both |
| M4 | Chart hardcodes secret name `<release>-auth0-credentials`; CLI note says `<release>-oidc-credentials` | Chart — rename |
| M5 | Chart mount path `/etc/mcp/secrets/auth0/` vs CLI-expected `/etc/mcp/secrets/oidc/` | Chart — rename |
| M6 | Chart `ConfigMap` always emits Pattern-A keys (`client_secret_file`, `jwt_signing_key_file`, `redis:` block) | Chart — branch on `oidc.authType` |
| M7 | Chart `Deployment` always mounts Pattern-A secrets | Chart — branch on `oidc.authType` |
| M8 | `bin/create-secrets.py` reads `./auth0-config.json` | Chart/mcp-base — rename to read `./oidc-config.json` (it's now the CLI that owns this file; scaffold shouldn't re-implement) |
| M9 | No `jwt.enabled` flag exists in `values.yaml` | Chart — add, default `true` for back-compat |
| M10 | Keycloak path in chart would need `realm_url` not `issuer` in `oidc.yaml` | Chart — branch in `configmap.yaml` |

None of these mismatches block basic Auth0 deployments today; they all
block Keycloak deployments.

---

## 8. Change list for `mcp-base-cli`

Implement in this order so each change is independently testable.

1. **Add `pattern` field to `oidc-config.json`.**
   Derive from `provider`: `keycloak` → `"remote"`, everything else →
   `"proxy"`. Existing files without the field: treat absence as `"proxy"`
   for back-compat.

2. **Stop writing `server_client` for Pattern B.**
   In `setup-oidc --provider keycloak`, omit the `server_client` block.
   If the user passed `--client-id`/`--client-secret` anyway, print a
   warning that they are unused at runtime.

3. **Emit `oidc.authType` in `oidc-values.yaml`.**
   `auth0` → `"auth0"`, `keycloak` → `"keycloak"`, all others → `"oidc"`.
   Drive this from the same `provider` field.

4. **Emit `redis.enabled` and `jwt.enabled` in `oidc-values.yaml`.**
   Pattern A → both `true`. Pattern B → both `false`. Always emit
   explicitly — do not rely on chart defaults.

5. **Make `create-secrets` a no-op for Pattern B.**
   Read `pattern` from `oidc-config.json`. If `"remote"`, print
   "Pattern B (Keycloak native DCR) — no Kubernetes secrets required"
   and exit 0. Do not create any Secret objects.

6. **Standardize the Pattern-A secret name.**
   Name the client-creds Secret `<release>-oidc-credentials` (not
   `-auth0-credentials`) regardless of provider. This matches what the
   chart will be changed to consume.

7. **Rename the CLI config file (optional, deferred).**
   `auth0-config.json` → `oidc-config.json`. The CLI already uses the new
   name; leave a compatibility shim that reads either for one release.

8. **Document the pattern in CLI help text.**
   `setup-oidc --help` should state which pattern each provider uses, and
   that Keycloak requires version ≥ 26.6.0.

---

## 9. Change list for `mcp-base` (chart + scaffold)

Paired with §8; track separately.

1. **Add `oidc.authType` to `values.yaml`** with default `"auth0"`.
2. **Add `jwt.enabled` to `values.yaml`** with default `true`.
3. **Rename Secret** `<release>-auth0-credentials` →
   `<release>-oidc-credentials` in `deployment.yaml` and any templates
   that reference it.
4. **Rename mount path** `/etc/mcp/secrets/auth0/` →
   `/etc/mcp/secrets/oidc/`.
5. **Branch `configmap.yaml` on `oidc.authType`:**
   emit Pattern A keys (`client_secret_file`, `jwt_signing_key_file`,
   `storage_encryption_key_file`, `redis:` block) only when
   `authType != "keycloak"`. For `"keycloak"` emit `realm_url` instead of
   `issuer` and `required_scopes`.
6. **Branch `deployment.yaml` on `oidc.authType`:**
   gate the `auth0-credentials` / `jwt-signing-key` volumes and
   volumeMounts behind `authType != "keycloak"`.
7. **Gate Redis subchart on `redis.enabled`** (likely already the case
   via the standard Helm dependency condition — verify).
8. **Delete or rewrite `bin/create-secrets.py`.** This functionality has
   moved to `mcp-base-cli create-secrets` and the scaffold should not
   ship a divergent copy. If kept for offline/CI use, change it to read
   `oidc-config.json` and honor `pattern: "remote"` as a no-op.
9. **Scaffold `oidc.yaml` loader** must tolerate both shapes (Pattern A
   keys vs Pattern B keys) and dispatch on `auth_type`.

---

## 10. Testing checklist

For each `auth_type`, end-to-end verification:

- [ ] `mcp-base setup-oidc --provider <p>` produces
  `oidc-config.json` with the correct `pattern` field.
- [ ] `oidc-values.yaml` has `oidc.authType`, `redis.enabled`,
  `jwt.enabled` set correctly.
- [ ] `mcp-base create-secrets` creates exactly the expected Secrets
  (2 for Pattern A, 0 for Pattern B).
- [ ] `helm template` with the produced values renders a ConfigMap
  containing the right `oidc.yaml` shape.
- [ ] `helm template` renders a Deployment mounting only the Secrets
  that exist for that pattern.
- [ ] Scaffolded server container starts, reads `/etc/mcp/oidc.yaml`,
  and successfully serves `/healthz`.
- [ ] MCP client registers via DCR (FastMCP-local for Pattern A,
  Keycloak-native for Pattern B) and calls at least one tool.

---

## 11. Non-goals

- Supporting Keycloak < 26.6.0 via `auth_type="keycloak"`. Use
  `auth_type="oidc"` for older Keycloak.
- Supporting a Pattern A Auth0 deployment *without* Redis. Redis is
  required for OAuth session persistence across replicas.
- Auto-migrating existing `auth0-config.json` installations. One-release
  compat shim is enough; document the rename.
