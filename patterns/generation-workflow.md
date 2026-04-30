# MCP Server Generation Workflow

This pattern describes how to use mcp-base to generate a complete MCP
server project. The workflow is **resource-first**: bulk artifact bytes
flow through MCP resources, tools return only compact coordination
metadata.

---

## CRITICAL ARTIFACT RETRIEVAL GATE (READ FIRST)

Artifact retrieval is a HARD GATE. **Invariant:** the scaffold is valid
only if each file on disk is byte-identical to the artifact stored at
generation time. Byte parity is checkable — every manifest entry carries
`sha256`.

### Retrieval paths, in priority order

1. **PRIMARY — Bulk bytes (resource):**
   `resources/read("scaffold://{project_id}/{path}")`
   Returns exact artifact bytes. Verify against `artifacts[i].sha256`.
   Bytes do NOT enter model context unless you explicitly read them.

2. **PRIMARY — Coordination metadata (tools):**
   `list_scaffold_artifact_metadata(project_id)` — compact per-artifact
   metadata for the whole scaffold (role, summary, customization
   relevance, symbols). No file contents.
   `read_scaffold_artifact_metadata(project_id, path)` — detailed
   metadata for one artifact, including dependencies and customization
   notes. No file contents.

3. **LAST-RESORT FALLBACK — do NOT use if `resources/read` works:**
   `read_scaffold_artifact(project_id, path)` returns the **full**
   artifact contents inside tool output and pulls every byte into the
   model context. For a typical scaffold (30+ files) this blows the
   context budget. This tool exists solely for MCP clients that cannot
   invoke `resources/read` at all — e.g. OpenAI's `codex_apps` proxy,
   which forwards only tools and drops resources/prompts entirely. If
   your client supports `resources/read`, using this tool is a bug:
   switch to the resource path. The integrity gate (sha256
   verification) is unchanged when you are forced to use this path.

### On ANY retrieval failure, STOP

Do NOT:
- Reconstruct files from memory
- Render templates as a substitute (`render_template` is **NOT** a fallback)
- Create placeholder files
- Infer contents from filenames
- Continue to Phase 2 (customization)
- Create `SCAFFOLD_INVENTORY.md` as if retrieval succeeded

Instead, create `SCAFFOLD_RETRIEVAL_FAILURE.md` (template at the bottom
of this page) and halt. A ready-to-use copy of this template is also
returned in the `failure_report_template` field of the
`generate_server_scaffold` response.

`SCAFFOLD_INVENTORY.md` may only be created after **100% artifact
retrieval with verified hashes**. If retrieval is incomplete or any hash
mismatches, create `SCAFFOLD_RETRIEVAL_FAILURE.md` instead.

---

## PHASE 1: RETRIEVE ALL ARTIFACTS, VERIFY, THEN CREATE SCAFFOLD_INVENTORY.md

Your Phase 1 deliverable is `SCAFFOLD_INVENTORY.md` — but it is only
produced **after** every artifact has been retrieved exactly and every
sha256 has been verified.

---

### Step 1: Generate the Scaffold

```python
result = await session.call_tool("generate_server_scaffold", {
    "server_name": "My Kubernetes Manager"
})

project_id   = result["project_id"]   # e.g., "my-kubernetes-manager-abc12345"
artifacts    = result["artifacts"]    # compact manifest: path, uri, sha256, role, ...
file_count   = result["file_count"]   # expected count (e.g., 34)
```

The tool output is a compact manifest — **no file contents**. Each
`artifacts[i]` entry has:

- `path` — file path within the project
- `uri` — `scaffold://{project_id}/{path}`
- `mime_type`, `size_bytes`, `sha256`, `hash_algorithm`
- `content_encoding` (`"utf-8"`), `line_endings` (`"lf"` / `"crlf"`)
- `executable` (bool), `permissions` (e.g. `"0755"` / `"0644"`)
- `post_write_actions` — list of commands to run after writing the file
  to disk (e.g., `["chmod +x bin/configure-make.py"]` for bin scripts;
  empty for regular files)
- `role` — e.g., `tools_module`, `server_entrypoint`, `helm_values`
- `customization_relevance` — `high` | `medium` | `low` | `none`
- `summary` — one-line description

Note: the generation manifest does **not** include Python API details
(symbols, exports, imports). Call `list_scaffold_artifact_metadata` or
`read_scaffold_artifact_metadata` when you're ready to customize — those
tools add the public API surface without loading file contents.

### Step 2: Retrieve Bytes via Resources and Verify Hashes

**This is the primary path. Tool output is not used for bulk bytes.**

```python
import hashlib, os, subprocess

retrieval_failures = []

for entry in artifacts:
    try:
        # PRIMARY: pull bytes via resources/read — stays out of model context
        # unless you read the returned object explicitly.
        resource = await session.read_resource(entry["uri"])
        content  = resource.contents[0].text
    except Exception as e:
        retrieval_failures.append((entry["path"], f"resources/read: {e}"))
        continue

    # Verify byte parity BEFORE writing to disk.
    actual_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if actual_sha256 != entry["sha256"]:
        retrieval_failures.append((
            entry["path"],
            f"sha256 mismatch: expected {entry['sha256']}, got {actual_sha256}",
        ))
        continue

    parent = os.path.dirname(entry["path"])
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(entry["path"], "w", encoding=entry["content_encoding"]) as f:
        f.write(content)

    # Apply operational metadata — permissions + post-write actions.
    os.chmod(entry["path"], int(entry["permissions"], 8))
    for cmd in entry.get("post_write_actions", []):
        subprocess.run(cmd, shell=True, check=True)

# RETRIEVAL GATE — check before writing SCAFFOLD_INVENTORY.md
if retrieval_failures:
    # STOP. Create SCAFFOLD_RETRIEVAL_FAILURE.md and halt.
    raise SystemExit("Retrieval failed — see SCAFFOLD_RETRIEVAL_FAILURE.md")
```

The `permissions` and `post_write_actions` fields replace the old
hardcoded `chmod +x bin/*` rule — the manifest now tells the agent
exactly which files need executable bits.

**Tool-only fallback** (clients that cannot invoke `resources/read`):

```python
# Only use when resources/read is unavailable. Accepts the context-bloat cost.
content = await session.call_tool("read_scaffold_artifact", {
    "project_id": project_id,
    "path": entry["path"],
})
# Verify sha256 the same way — the integrity gate is unchanged.
```

### Step 3: Collect the API Surface (No File Contents)

`list_scaffold_artifact_metadata` returns, in one compact call, the
**public API surface** of every Python module in the scaffold along
with role/relevance/summary fields — no file contents. This is the
materialization contract: it is enough to write new code that imports
from and calls into the scaffold modules without ever pulling their
bytes into model context.

```python
meta = await session.call_tool("list_scaffold_artifact_metadata", {
    "project_id": project_id,
})

# Per-entry fields:
#   path, uri, mime_type, size_bytes, sha256, hash_algorithm,
#   content_encoding, line_endings,
#   executable, permissions, post_write_actions,
#   role, customization_relevance, summary,
#   customization_notes, verification_notes,
#   (Python files:) symbols, exports
#
# Each `symbols[i]` entry is AST-extracted and carries:
#   name, kind (function / async_function / class),
#   line_hint, signature, decorators, summary (first line of docstring)
# For classes, `methods` is a list of the same shape covering public
# methods and __init__.
```

`read_scaffold_artifact_metadata(project_id, path)` returns the same
shape for a single file and additionally includes an `imports` list
(top-level modules the file imports). Call it before customizing a
specific file so you can see what it already depends on.

If you still need to see the file contents, read the local copy
written in Step 2 rather than calling any tool — the local file is
byte-identical (sha256-verified) and doesn't round-trip through model
context.

### Step 4: Create SCAFFOLD_INVENTORY.md

**This is the Phase 1 deliverable. It is written only after 100%
retrieval with verified hashes.**

```markdown
# Scaffold Inventory

## Verification Checklist
- [ ] File count: Retrieved ___ of 34 expected files
- [ ] All files written to disk with exact content (sha256 verified)
- [ ] All files have inventory entries below
- [ ] No placeholders created
- [ ] No files skipped

## File Inventory

### src/my_kubernetes_manager_server.py
- Role: server_entrypoint
- Customization relevance: medium
- Size: 4523 bytes
- sha256: <hash>
- Symbols: main, create_app, register_routes, handle_mcp, health_check

### src/my_kubernetes_manager_tools.py
- Role: tools_module
- Customization relevance: high
- Size: 2341 bytes
- sha256: <hash>
- Symbols: register_tools, example_tool_impl

[... entry for EVERY file ...]
```

The `role`, `customization_relevance`, and `symbols` values come
directly from `list_scaffold_artifact_metadata` — you don't need to
re-derive them.

---

## CRITICAL: Why This Approach Prevents Shortcuts

| Temptation | Why it fails | What to do instead |
|-------------|---------|--------------|
| Skip some files | Incomplete scaffold = broken Phase 2 | Loop over every `artifacts[i]` entry |
| Skip sha256 check | Undetected bit-rot or partial reads | Verify every file before writing |
| Use tool path "because it's easier" | Pulls every file's bytes into context | `resources/read` keeps bytes out of context |
| Skip the inventory | No proof of completeness | `SCAFFOLD_INVENTORY.md` IS the deliverable |

**You cannot fake sha256 hashes or symbol lists without actually
retrieving the files.**

---

## PHASE 1 VERIFICATION (Built Into Inventory)

The verification checklist at the top of SCAFFOLD_INVENTORY.md must show:

- [ ] `actual_count == file_count` (e.g., 34 == 34)
- [ ] All files from `artifacts[]` exist on disk
- [ ] Every written file's sha256 matches the manifest
- [ ] No placeholders created
- [ ] No files skipped

**If verification fails, your Phase 2 customizations WILL FAIL.**

---

## Expected Directory Structure

After Phase 1, you should have:

```
./                                  # Current directory (NOT a subdirectory!)
├── SCAFFOLD_INVENTORY.md           # YOUR PHASE 1 DELIVERABLE
├── src/
│   ├── my_kubernetes_manager_server.py    # Main server entry point
│   ├── my_kubernetes_manager_test_server.py  # Test server (no auth)
│   ├── my_kubernetes_manager_tools.py     # Your tools go here
│   ├── auth_fastmcp.py
│   ├── auth_oidc.py
│   ├── mcp_context.py
│   ├── prompt_registry.py
│   └── user_hash.py
├── bin/
│   └── configure-make.py           # Makefile configuration (creates make.env)
├── test/
│   ├── test-mcp.py                 # Test runner
│   ├── get-user-token.py           # Token helper
│   ├── mcp-auth-proxy.py           # Auth proxy
│   └── plugins/
│       ├── __init__.py
│       ├── test_list_resources.py
│       ├── test_read_resource.py
│       ├── test_list_prompts.py
│       └── test_example.py
├── chart/
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── .helmignore
│   └── templates/
│       ├── _helpers.tpl
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── configmap.yaml
│       ├── prompts-configmap.yaml
│       ├── serviceaccount.yaml
│       ├── rolebinding.yaml
│       ├── ingress.yaml
│       ├── hpa.yaml
│       └── NOTES.txt
├── Dockerfile                        # Production container
├── Dockerfile.test                   # Test container (no auth)
├── Makefile                          # Includes build-test, push-test targets
└── requirements.txt
```

---

## PHASE 2: CUSTOMIZE USING INVENTORY (ONLY AFTER PHASE 1 COMPLETE)

**Given SCAFFOLD_INVENTORY.md showing all scaffold components:**

Focus customization on files with `customization_relevance` of `high`
or `medium`. For those files, `read_scaffold_artifact_metadata` gives
you dependencies and customization notes before you read the file
locally.

### Step 1: Implement Your Tools

Edit `src/*_tools.py` (role `tools_module`, high customization
relevance) to add your specific functionality:

```python
# In src/my_kubernetes_manager_tools.py

@mcp.tool()
async def list_pods(namespace: str = "default") -> str:
    """List pods in a namespace."""
    # Your implementation here
    pass
```

### Step 2: Add Dependencies (if needed)

```bash
echo "kubernetes" >> requirements.txt
```

### Step 3: Test Locally

```bash
pip install -r requirements.txt
python src/my_kubernetes_manager_server.py --port 4200
```

### Step 4: Deploy

```bash
python bin/configure-make.py
mcp-base setup-oidc
make build && make push
make helm-install
```

---

## Common Mistakes (All Violate Phase 1 Rules)

### "I used `read_scaffold_artifact` for every file"

**Problem**: Every call pulls the full file contents into model context.
For a 34-file scaffold this can blow the context budget and push other
tool results out.
**Solution**: Use `resources/read("scaffold://...")` as the primary
bulk-bytes path. Reserve `read_scaffold_artifact` for tool-only proxy
clients.

### "I skipped the sha256 check"

**Problem**: Silent truncation or charset corruption produces a
scaffold that looks written but won't run.
**Solution**: Compute `sha256(content)` before writing and compare to
`entry["sha256"]`. A mismatch is a retrieval failure.

### "I only retrieved src/ files"

**Problem**: Impatience led to skipping files.
**Solution**: The loop must iterate through EVERY entry in `artifacts`.
No exceptions.

### "I wrote my own Dockerfile"

**Problem**: Eagerness to "improve" led to deviation from scaffold.
**Solution**: Use EXACT content from the artifact store. Customize in
Phase 2 if needed.

### "I created a project subdirectory"

**Problem**: Writing to `./my-kubernetes-manager/src/...` instead of `./src/...`
**Solution**: Write to current directory (.) using exact paths from `artifacts[i].path`.

### "I used bash heredocs to write files faster"

**Problem**: Bypassing the retrieval API creates untested, inconsistent files.
**Solution**: Always retrieve via `resources/read` (or the fallback tool).

### "Retrieval failed so I rendered the template instead"

**Problem**: Template rendering is NOT a substitute for artifact retrieval.
Rendered templates are unparameterized defaults — the scaffold artifacts
include project-specific values the template doesn't know about.
**Solution**: If retrieval fails, STOP and create
`SCAFFOLD_RETRIEVAL_FAILURE.md`. Then retry generation or escalate. The
retrieval gate is absolute.

### "I reconstructed the missing file from memory"

**Problem**: Memory-reconstruction silently violates the exact-artifact
invariant and produces a scaffold that no longer matches what
`generate_server_scaffold` actually emitted.
**Solution**: Never reconstruct. Record the failure and halt.

### "I started adding my tools before all files were written"

**Problem**: Mixing Phase 1 and Phase 2 causes confusion.
**Solution**: Complete ALL of Phase 1 (including SCAFFOLD_INVENTORY.md) before starting Phase 2.

### "I skipped creating SCAFFOLD_INVENTORY.md"

**Problem**: Without the inventory, there's no proof Phase 1 was completed correctly.
**Solution**: The inventory IS the deliverable. Create it with full details for every file.

---

## Utility Scripts

### Scripts in Scaffold vs mcp-base CLI

**Included in scaffold:**
- `bin/configure-make.py` - Generates make.env for Makefile configuration

**Available via mcp-base CLI** (not in scaffold):
```bash
pip install mcp-base
mcp-base --help

# Available commands:
mcp-base add-user          # Add Auth0 users
mcp-base create-secrets    # Create Kubernetes secrets
mcp-base setup-oidc        # Configure OIDC provider
mcp-base setup-rbac        # Set up Kubernetes RBAC
```

---

## Summary: The Golden Rule

**Resources for bytes. Tools for metadata. SCAFFOLD_INVENTORY.md is the
Phase 1 deliverable.**

In Phase 1 you pull bytes via `resources/read`, verify every sha256,
write to disk, and — only after 100% verified retrieval — produce
`SCAFFOLD_INVENTORY.md` from `list_scaffold_artifact_metadata`.

In Phase 2 you customize using the inventory, prioritizing files with
`customization_relevance` of `high` or `medium`.

**But:** `SCAFFOLD_INVENTORY.md` may only be created after 100%
retrieval with verified hashes. If even one artifact fails to retrieve
or its hash mismatches, the deliverable is
`SCAFFOLD_RETRIEVAL_FAILURE.md` (template below), not a partial
inventory.

---

## SCAFFOLD_RETRIEVAL_FAILURE.md Template

Use this when any artifact cannot be retrieved or fails hash
verification. Do not write scaffold files if this report applies. A
copy of this template is also returned in the `failure_report_template`
field of the `generate_server_scaffold` response.

```markdown
# Scaffold Retrieval Failure

- Project ID: <project_id>
- Expected files: <file_count>
- Retrieved files: <count>
- Failed files: <count>
- Files written to disk: none

## Failed Artifact Reads

| Path | Error |
| --- | --- |
| <path> | <exact error message or sha256 mismatch> |

## Conclusion

Scaffold generation returned a manifest, but scaffold artifacts were
not retrievable via `resources/read("scaffold://...")`, or one or more
retrieved artifacts failed sha256 verification. No scaffold files were
written because doing so would violate the exact-artifact invariant.

## Suggested Next Step

Verify that the MCP server exposes `scaffold://{project_id}/{path}` as
concrete MCP resources, and that the `project_id` has not expired.
Retry generation if the server was restarted between calls. If the
client cannot invoke `resources/read` at all, fall back to
`read_scaffold_artifact` as a compatibility path (accepting the
context-bloat cost) and verify sha256 the same way.
```
