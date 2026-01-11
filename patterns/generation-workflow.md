# MCP Server Generation Workflow

This pattern describes how to use mcp-base to generate a complete MCP server project.

## Two-Phase Workflow

The workflow is divided into two distinct phases with a clear checkpoint between them.

---

## PHASE 1: SCAFFOLD RETRIEVAL (MECHANICAL - NO CREATIVITY)

**Mindset**: This is MECHANICAL work. Think: copy machine, not architect.
Think: assembling IKEA furniture - follow instructions exactly.

### Step 1: Generate the Scaffold

```python
result = await session.call_tool("generate_server_scaffold", {
    "server_name": "My Kubernetes Manager"
})

project_id = result["project_id"]   # e.g., "my-kubernetes-manager-abc12345"
files = result["files"]             # List of ALL file paths (e.g., 33 files)
file_count = result["file_count"]   # Expected count
```

### Step 2: Retrieve and Write EVERY File

**This loop is MANDATORY. No exceptions. No shortcuts.**

```python
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

    print(f"✓ {file_path}")
```

### Step 3: Verify File Count

```bash
find . -type f | wc -l  # Must match file_count
```

---

## CRITICAL: DO NOT During Phase 1

These are common failure modes caused by impatience/eagerness:

| Anti-Pattern | Why It's Wrong |
|-------------|----------------|
| Write custom content instead of using get_artifact | Scaffold content is tested and complete |
| Use bash heredocs to "save time" | Creates inconsistent, untested files |
| Skip files thinking "I'll write these faster myself" | Missing files cause deployment failures |
| Start customizing before ALL files are written | Leads to confusion about what was scaffold vs custom |
| Create documentation before scaffold is complete | Distraction from the core task |
| Get distracted by other tasks | Focus destroyer - complete Phase 1 first |

**If you catch yourself doing any of these, STOP immediately.**

---

## CHECKPOINT: Phase 1 Complete?

Before proceeding to Phase 2, verify:

- [ ] All files from files list retrieved via get_artifact
- [ ] All files written to current directory (.)
- [ ] No custom content written (only scaffold content)
- [ ] File count matches expected count
- [ ] Directory structure matches expected structure (see below)

**DO NOT proceed to Phase 2 until all checkboxes are true.**

---

## Expected Directory Structure

After Phase 1, you should have:

```
./                                  # Current directory (NOT a subdirectory!)
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
│   └── make-config.py              # Configuration generator
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

## PHASE 2: CUSTOMIZATION (ONLY AFTER PHASE 1 COMPLETE)

**Mindset**: Now you can be creative. But only AFTER Phase 1 is 100% complete.

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
python bin/make-config.py
make build && make push
make helm-install
```

---

## Common Mistakes (All Violate Phase 1 Rules)

### ❌ "I only retrieved src/ files"

**Problem**: Impatience led to skipping files.
**Solution**: The loop must iterate through EVERY file in the list. No exceptions.

### ❌ "I wrote my own Dockerfile"

**Problem**: Eagerness to "improve" led to deviation from scaffold.
**Solution**: Use EXACT content from get_artifact. Customize in Phase 2 if needed.

### ❌ "I created a project subdirectory"

**Problem**: Writing to `./my-kubernetes-manager/src/...` instead of `./src/...`
**Solution**: Write to current directory (.) using exact paths from files list.

### ❌ "I used bash heredocs to write files faster"

**Problem**: Bypassing get_artifact creates untested, inconsistent files.
**Solution**: Always use get_artifact to retrieve scaffold content.

### ❌ "I started adding my tools before all files were written"

**Problem**: Mixing Phase 1 and Phase 2 causes confusion.
**Solution**: Complete ALL of Phase 1 before starting Phase 2.

---

## Utility Scripts

### Scripts in Scaffold vs mcp-base CLI

**Included in scaffold:**
- `bin/make-config.py` - Generates Auth0 config and Helm values

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

**Phase 1 is MECHANICAL. Phase 2 is CREATIVE.**

In Phase 1, you are a copy machine. You retrieve and write. Nothing more.
In Phase 2, you are an architect. You customize and extend.

Never mix the two phases.
