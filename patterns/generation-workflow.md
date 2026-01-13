# MCP Server Generation Workflow

This pattern describes how to use mcp-base to generate a complete MCP server project.

---

## PHASE 1: CREATE SCAFFOLD_INVENTORY.md (REQUIRED DELIVERABLE)

Your **ONLY** goal in Phase 1 is to produce `SCAFFOLD_INVENTORY.md`.

This document IS your deliverable. Quality determines success.

**Why this approach works:**
- "Create inventory" feels productive, not like busywork
- Line counts and function names are verifiable - you can't fake them
- Incomplete inventory = broken Phase 2 customization
- The inventory preserves knowledge even if artifacts expire

---

### Step 1: Generate the Scaffold

```python
result = await session.call_tool("generate_server_scaffold", {
    "server_name": "My Kubernetes Manager"
})

project_id = result["project_id"]   # e.g., "my-kubernetes-manager-abc12345"
files = result["files"]             # List of ALL file paths
file_count = result["file_count"]   # Expected count (e.g., 34)
```

### Step 2: Retrieve and Write EVERY File

**This loop is MANDATORY. No exceptions. No shortcuts.**

```python
inventory_entries = []

for file_path in files:
    # Get EXACT content from artifact store
    content = await session.call_tool("get_artifact", {
        "project_id": project_id,
        "path": file_path
    })

    # Create parent directories if needed
    parent_dir = os.path.dirname(file_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # Write EXACT content to current directory
    with open(file_path, "w") as f:
        f.write(content)

    # Collect inventory data (REQUIRED)
    lines = content.count('\n') + 1
    size_bytes = len(content.encode('utf-8'))

    # Extract first 5 function/class names for code files
    names = []
    if file_path.endswith('.py'):
        for line in content.split('\n'):
            if line.startswith('def ') or line.startswith('class ') or line.startswith('async def '):
                name = line.split('(')[0].replace('def ', '').replace('class ', '').replace('async ', '').strip()
                names.append(name)
                if len(names) >= 5:
                    break

    inventory_entries.append({
        "path": file_path,
        "lines": lines,
        "bytes": size_bytes,
        "names": names
    })

    print(f"✓ {file_path}")
```

### Step 3: Make Bin Scripts Executable

```bash
chmod +x bin/*
```

### Step 4: Create SCAFFOLD_INVENTORY.md

**This is the deliverable. Quality of this document determines success.**

```markdown
# Scaffold Inventory

## Verification Checklist
- [ ] File count: Retrieved ___ of 34 expected files
- [ ] All files written to disk with exact content
- [ ] All files have inventory entries below
- [ ] No placeholders created
- [ ] No files skipped

## File Inventory

### src/my_kubernetes_manager_server.py
- Lines: 142
- Bytes: 4523
- Defines: main, create_app, register_routes, handle_mcp, health_check

### src/my_kubernetes_manager_tools.py
- Lines: 89
- Bytes: 2341
- Defines: register_tools, example_tool_impl

[... entry for EVERY file ...]
```

---

## CRITICAL: Why This Approach Prevents Shortcuts

| Old Approach | Problem | New Approach |
|-------------|---------|--------------|
| "Copy all files" | Feels like busywork, tempting to skip | "Create inventory document" feels productive |
| Verification is a gate | Can rationalize skipping the gate | Inventory IS the deliverable |
| No verifiable output | Easy to claim "done" without doing | Line counts, function names are verifiable |
| Phase 2 seems like "real work" | Pressure to rush to Phase 2 | Phase 2 quality depends on inventory quality |

**You cannot fake line counts or function names without reading the files.**

---

## PHASE 1 VERIFICATION (Built Into Inventory)

The verification checklist at the top of SCAFFOLD_INVENTORY.md must show:

- [ ] `actual_count == file_count` (e.g., 34 == 34)
- [ ] All files from files list exist on disk
- [ ] All files have inventory entries with line counts and names
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

Refer to the inventory to understand what exists before modifying.
Your customizations WILL FAIL if Phase 1 inventory was incomplete.

### Step 1: Implement Your Tools

Edit `src/*_tools.py` to add your specific functionality:

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
python src/my_kubernetes_manager_server.py --port 4207
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

### "I only retrieved src/ files"

**Problem**: Impatience led to skipping files.
**Solution**: The loop must iterate through EVERY file in the list. No exceptions.

### "I wrote my own Dockerfile"

**Problem**: Eagerness to "improve" led to deviation from scaffold.
**Solution**: Use EXACT content from get_artifact. Customize in Phase 2 if needed.

### "I created a project subdirectory"

**Problem**: Writing to `./my-kubernetes-manager/src/...` instead of `./src/...`
**Solution**: Write to current directory (.) using exact paths from files list.

### "I used bash heredocs to write files faster"

**Problem**: Bypassing get_artifact creates untested, inconsistent files.
**Solution**: Always use get_artifact to retrieve scaffold content.

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

**Phase 1 deliverable is SCAFFOLD_INVENTORY.md. Phase 2 uses the inventory.**

In Phase 1, you retrieve files AND create a detailed inventory. The inventory proves completeness.
In Phase 2, you customize using the inventory as your reference.

Never skip the inventory. It's not optional - it IS the deliverable.
