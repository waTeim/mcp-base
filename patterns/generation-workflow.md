# MCP Server Generation Workflow

This pattern describes how to use mcp-base to generate a complete MCP server project.

## Critical Concept: Resources vs Tools

**⚠️ IMPORTANT**: Reading MCP resources does NOT create files. Resources provide templates and documentation as read-only content. To create actual source files, you must call the generation tools.

### What Happens When You Read a Resource

```python
# Reading a template resource
content = await session.read_resource("template://server/entry_point.py")
# Result: You get the Jinja2 template content as a string
# Disk state: NO FILES CREATED

# Reading a pattern resource
docs = await session.read_resource("pattern://fastmcp-tools")
# Result: You get pattern documentation as a string
# Disk state: NO FILES CREATED
```

**Resources are informational only** - they help you understand what will be generated, but they don't generate anything.

### What Happens When You Call Generation Tools

```python
# Calling the scaffold generation tool
result = await session.call_tool("generate_server_scaffold", {
    "server_name": "My Kubernetes Manager"
})
# Result: A complete project directory is created on disk
# Disk state: my-kubernetes-manager/ directory with all source files exists
```

## Complete Generation Workflow

### Option 1: Full Scaffold Generation (Recommended)

Generate a complete, ready-to-deploy MCP server project:

```python
# 1. Call generate_server_scaffold
result = await session.call_tool("generate_server_scaffold", {
    "server_name": "My Kubernetes Manager",
    "port": 8000,
    "default_namespace": "default",
    "operator_cluster_roles": "cluster-admin",
    "include_helm": True,
    "include_test": True,
    "include_bin": True,
    "output_description": "summary"
})

# 2. The tool creates this directory structure:
# my-kubernetes-manager/
# ├── src/
# │   ├── my_kubernetes_manager.py
# │   ├── my_kubernetes_manager_test_server.py
# │   ├── my_kubernetes_manager_tools.py
# │   ├── auth_fastmcp.py
# │   ├── auth_oidc.py
# │   ├── mcp_context.py
# │   └── user_hash.py
# ├── test/
# │   └── plugins/
# ├── chart/
# │   ├── Chart.yaml
# │   └── values.yaml
# ├── Dockerfile
# ├── Makefile
# └── requirements.txt

# 3. Customize the generated code
# Edit my_kubernetes_manager_tools.py to add your Kubernetes operations:
# - Add tool functions for pod management, deployment operations, etc.
# - Add resource registrations for configuration data
```

### Option 2: Individual Template Rendering

For more control, render individual templates:

```python
# 1. Render a specific template
entry_point = await session.call_tool("render_template", {
    "template_path": "server/entry_point.py.j2",
    "server_name": "My Kubernetes Manager",
    "port": 8000,
    "default_namespace": "default"
})

# 2. Write the rendered content to a file yourself
# (You must do this - render_template returns a string)
with open("src/my_kubernetes_manager.py", "w") as f:
    f.write(entry_point)
```

### Option 3: Hybrid Approach

Generate scaffold, then customize specific files:

```python
# 1. Generate base scaffold
await session.call_tool("generate_server_scaffold", {
    "server_name": "My Manager",
    "include_test": False  # Skip test framework initially
})

# 2. Later, render test framework components individually
test_plugin = await session.call_tool("render_template", {
    "template_path": "test/test_list_resources.py.j2",
    "server_name": "My Manager"
})

# 3. Write to the appropriate location
with open("test/plugins/test_list_resources.py", "w") as f:
    f.write(test_plugin)
```

## Understanding the Generated Code

### What You Get vs What You Must Add

**Generated automatically:**
- Server entry points (main + test servers)
- Authentication middleware (OAuth + OIDC)
- Context extraction and user hashing
- Test framework structure
- Helm chart with Redis session storage
- Dockerfile and build configuration

**You must add:**
- Actual tool implementations in `*_tools.py`
- Kubernetes API client code for your operations
- Resource registrations for your configuration data
- Test plugins for your custom tools

### Example: Adding Your First Tool

After generating the scaffold, edit `my_kubernetes_manager_tools.py`:

```python
def register_tools(mcp):
    """Register all tools with the MCP server instance."""

    @mcp.tool(name="list_pods")
    @with_mcp_context
    async def list_pods(ctx: MCPContext, namespace: str = "default") -> str:
        """
        List all pods in the specified namespace.

        Args:
            namespace: Kubernetes namespace to list from

        Returns:
            Formatted list of pods
        """
        # Add your Kubernetes API call here
        from kubernetes import client, config
        config.load_incluster_config()
        v1 = client.CoreV1Api()

        pods = v1.list_namespaced_pod(namespace=namespace)

        result = []
        for pod in pods.items:
            result.append({
                "name": pod.metadata.name,
                "status": pod.status.phase,
                "namespace": pod.metadata.namespace
            })

        return json.dumps(result, indent=2)
```

## Common Misconceptions

### ❌ "I read template://server/tools.py so now I have a tools.py file"

**Reality**: You only read the template content. No file exists until you:
1. Call `generate_server_scaffold()`, OR
2. Call `render_template()` and write the output yourself

### ❌ "I'll just read all the templates and assemble them manually"

**Why this is harder**: You would need to:
1. Read each template individually
2. Provide all Jinja2 variables correctly
3. Create the directory structure
4. Write each file to the correct location
5. Ensure naming conventions match across files

**Better approach**: Use `generate_server_scaffold()` which does all of this for you.

### ❌ "The scaffold includes my Kubernetes tools"

**Reality**: The scaffold includes:
- Server infrastructure (authentication, context, etc.)
- A skeleton `*_tools.py` with `register_tools()` and `register_resources()` functions
- Example/placeholder tool implementations

You must add your actual Kubernetes operations (list pods, create deployments, etc.) to the `*_tools.py` file.

## Verification Steps

After generation, verify the project was created:

```bash
# Check directory structure
ls -la my-kubernetes-manager/

# Should see:
# src/
# test/
# chart/
# Dockerfile
# Makefile
# requirements.txt

# Check main files exist
ls -la my-kubernetes-manager/src/

# Should see:
# my_kubernetes_manager.py
# my_kubernetes_manager_test_server.py
# my_kubernetes_manager_tools.py
# auth_fastmcp.py
# auth_oidc.py
# mcp_context.py
# user_hash.py
```

## Next Steps After Generation

1. **Review generated code** - Understand the dual-server pattern
2. **Add your tools** - Edit `*_tools.py` to add Kubernetes operations
3. **Configure authentication** - Set up Auth0 application and API
4. **Test locally** - Run the main server and test with MCP Inspector
5. **Write test plugins** - Add tests for your custom tools
6. **Build container** - Use provided Dockerfile
7. **Deploy to Kubernetes** - Use Helm chart with your values

## Best Practices

1. **Always use `generate_server_scaffold()` first** - Don't try to assemble templates manually
2. **Customize the generated code** - The scaffold is a starting point, not a finished product
3. **Preserve the dual-server pattern** - Both servers should import from `*_tools.py`
4. **Add tests as you add tools** - Write test plugins for each new tool
5. **Use the reference implementation** - See `example/cnpg-mcp/` for a complete working example

## Troubleshooting

### "Where are my source files?"

- Check that you called `generate_server_scaffold()`, not just read resources
- Check the output directory path from the tool result
- Verify you have write permissions to the target directory

### "The generated server doesn't have my tools"

- Expected - you must add your tools to `*_tools.py`
- The scaffold provides infrastructure, you add business logic

### "Can I regenerate if I made a mistake?"

- Yes, but it will overwrite existing files
- Consider using version control (git) before regeneration
- Or generate to a new directory and copy specific files
