# MCP Server Generation Workflow

This pattern describes how to use mcp-base to generate a complete MCP server project.

## Critical Concept: Artifact-Based Generation

**IMPORTANT**: The `generate_server_scaffold()` tool returns an artifact manifest - it does NOT write files directly to disk. You must:
1. Call `generate_server_scaffold()` to create the artifact set
2. Retrieve ALL files using `get_artifact(project_id, path)`
3. Write each file to the CURRENT DIRECTORY (.) preserving paths

### What Happens When You Call Generation Tools

```python
# 1. Call generate_server_scaffold - creates artifacts in memory
result = await session.call_tool("generate_server_scaffold", {
    "server_name": "My Kubernetes Manager"
})
# Result: Returns project_id, file list, and metadata
# Disk state: NO FILES CREATED YET

project_id = result["project_id"]   # e.g., "my-kubernetes-manager-abc12345"
files = result["files"]             # List of all file paths

# 2. Retrieve and write EACH file
for file_path in files:
    content = await session.call_tool("get_artifact", {
        "project_id": project_id,
        "path": file_path
    })
    # Write to current directory: ./{file_path}
    write_file(f"./{file_path}", content)
# Disk state: All files now exist in current directory
```

## Complete Generation Workflow

### Step 1: Generate the Scaffold

```python
result = await session.call_tool("generate_server_scaffold", {
    "server_name": "My Kubernetes Manager",
    "port": 4207,
    "default_namespace": "default",
    "operator_cluster_roles": "cluster-admin",
    "include_helm": True,
    "include_test": True
})

project_id = result["project_id"]
files_list = result["files"]
print(f"Generated {len(files_list)} files")
```

### Step 2: Retrieve and Write ALL Files

**CRITICAL**: You MUST retrieve and write ALL files, not just a subset.

```python
for file_path in files_list:
    # Get file content from artifact store
    content = await session.call_tool("get_artifact", {
        "project_id": project_id,
        "path": file_path
    })

    # Create parent directories if needed
    parent_dir = os.path.dirname(file_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # Write to current directory
    with open(file_path, "w") as f:
        f.write(content)
```

### Step 3: Verify the Directory Structure

After writing all files, you should have:

```
./                                  # Current directory (NOT a subdirectory!)
├── src/
│   ├── my_kubernetes_manager_server.py    # Main server entry point
│   ├── my_kubernetes_manager_test_server.py
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
│       ├── ingress.yaml              # Ingress IS included!
│       ├── hpa.yaml
│       └── NOTES.txt
├── Dockerfile
├── Makefile
└── requirements.txt
```

## Utility Scripts

### Scripts in Scaffold vs mcp-base CLI

**Included in scaffold:**
- `bin/make-config.py` - Generates Auth0 config and Helm values (coordinates with Dockerfile/Makefile)

**Available via mcp-base CLI** (not in scaffold):
```bash
pip install mcp-base
mcp-base --help

# Available commands:
mcp-base add-user          # Add Auth0 users
mcp-base create-secrets    # Create Kubernetes secrets
mcp-base setup-oidc        # Configure OIDC provider (Auth0, etc.)
mcp-base setup-rbac        # Set up Kubernetes RBAC
```

## Common Mistakes

### ❌ "I only retrieved src/ files"

**Problem**: The scaffold includes critical files in bin/, test/, chart/, and root directory.

**Solution**: Always iterate through the ENTIRE `files` list and retrieve every file.

### ❌ "I created a project subdirectory"

**Problem**: Writing to `./my-kubernetes-manager/src/...` instead of `./src/...`

**Solution**: Write files directly to the current directory (.) using the exact paths from the files list.

### ❌ "The ingress template is missing"

**Problem**: User didn't retrieve all files from the artifact store.

**Solution**: The ingress template IS included at `chart/templates/ingress.yaml`. Make sure you retrieve ALL files.

### ❌ "The test directory only has plugins/"

**Problem**: User only retrieved some test files.

**Solution**: The test/ directory includes:
- `test/test-mcp.py` - Main test runner
- `test/get-user-token.py` - Token helper
- `test/mcp-auth-proxy.py` - Auth proxy
- `test/plugins/__init__.py` - Plugin base
- `test/plugins/test_*.py` - Test plugins

Retrieve ALL of these files.

## Deployment Workflow

After writing all files:

```bash
# 1. Generate configuration (creates auth0-config.json, helm-values.yaml)
python bin/make-config.py

# 2. Install dependencies
pip install -r requirements.txt

# 3. Test locally
python src/my_kubernetes_manager_server.py --port 4207

# 4. Build and push container
make build
make push

# 5. Create Kubernetes secrets
pip install mcp-base
mcp-base create-secrets --namespace mcp --release-name my-kubernetes-manager

# 6. Deploy with Helm
make helm-install
```

## Understanding the Generated Code

### What You Get vs What You Must Add

**Generated automatically:**
- Server entry points (main + test servers)
- Authentication middleware (OAuth + OIDC)
- Context extraction and user hashing
- Test framework structure with base plugins
- Complete Helm chart with all templates (including ingress!)
- Dockerfile and build configuration
- Configuration generator (bin/make-config.py)

**You must add:**
- Actual tool implementations in `*_tools.py`
- Kubernetes API client code for your operations
- Resource registrations for your configuration data
- Test plugins for your custom tools

## Best Practices

1. **Always retrieve ALL files** - Don't skip files thinking they're optional
2. **Write to current directory (.)** - Don't create a project subdirectory
3. **Use bin/make-config.py** - Generates configuration before deployment
4. **Use mcp-base CLI** - For other utility tasks (create-secrets, setup-rbac, etc.)
5. **Verify file count** - Check that files written matches `file_count` in result
