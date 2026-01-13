"""
MCP Base Server - Tool Implementations

This module contains all tool implementations for the mcp-base server.
Tools are decorated with @mcp.tool() and follow the standard pattern.

The mcp instance is passed in via register_tools() to avoid circular imports.
"""

import json
import re
import uuid
from pathlib import Path
from typing import Optional, Literal, List, Dict, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from artifact_store import artifact_store, get_mime_type_for_path

# ============================================================================
# Path Configuration
# ============================================================================

# In development: __file__ is in src/, BASE_DIR is parent of src/
# In container: __file__ is in /app/, BASE_DIR is /app/
# Both scenarios work with parent.parent in dev, but only parent in container
# Use parent.parent for dev (src/ -> workspaces/mcp-base/), then check if templates exists
# If not, use parent (container scenario)
_possible_base = Path(__file__).parent.parent
if not (_possible_base / "templates").exists():
    _possible_base = Path(__file__).parent

BASE_DIR = _possible_base
TEMPLATES_DIR = BASE_DIR / "templates"
PATTERNS_DIR = BASE_DIR / "patterns"

# ============================================================================
# Jinja2 Environment
# ============================================================================

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(['html', 'xml']),
    trim_blocks=True,
    lstrip_blocks=True
)

# ============================================================================
# Utility Functions
# ============================================================================

def to_snake_case(name: str) -> str:
    """Convert name to snake_case."""
    s = re.sub(r'[-\s]+', '_', name)
    s = re.sub(r'([a-z])([A-Z])', r'\1_\2', s)
    return s.lower()


def to_kebab_case(name: str) -> str:
    """Convert name to kebab-case."""
    s = re.sub(r'[_\s]+', '-', name)
    s = re.sub(r'([a-z])([A-Z])', r'\1-\2', s)
    return s.lower()


def to_pascal_case(name: str) -> str:
    """Convert name to PascalCase."""
    parts = re.split(r'[-_\s]+', name)
    return ''.join(word.capitalize() for word in parts)


# ============================================================================
# Tool Implementations
# ============================================================================

async def list_templates_impl() -> str:
    """
    List all available templates for MCP server construction.

    Returns a categorized list of templates with descriptions.
    Use this to discover what templates are available before
    generating server scaffolding.

    Returns:
        Formatted list of available templates by category
    """
    result = "# Available Templates\n\n"

    # Server templates
    result += "## Server Templates\n"
    result += "- `server/entry_point.py.j2` - Main server entry point (HTTP transport)\n"
    result += "- `server/auth_fastmcp.py.j2` - FastMCP Auth0 provider configuration\n"
    result += "- `server/auth_oidc.py` - Generic OIDC provider (as-is)\n"
    result += "- `server/mcp_context.py` - MCPContext and with_mcp_context decorator\n"
    result += "- `server/user_hash.py` - User ID generation from JWT\n"
    result += "- `server/tools.py.j2` - Tool implementation skeleton\n"
    result += "- `server/prompt_registry.py.j2` - Versioned prompt management with hot-reload\n\n"

    # Container templates
    result += "## Container Templates\n"
    result += "- `container/Dockerfile.j2` - Production container build\n"
    result += "- `container/Dockerfile.test.j2` - Test container build (no auth)\n"
    result += "- `container/requirements.txt` - Python dependencies (as-is)\n\n"

    # Helm templates
    result += "## Helm Chart Templates\n"
    result += "- `helm/Chart.yaml.j2` - Chart metadata with Redis dependency\n"
    result += "- `helm/values.yaml.j2` - Default values\n"
    result += "- `helm/templates/_helpers.tpl.j2` - Template helpers\n"
    result += "- `helm/templates/deployment.yaml.j2` - Kubernetes deployment\n"
    result += "- `helm/templates/service.yaml.j2` - Kubernetes service\n"
    result += "- `helm/templates/configmap.yaml.j2` - OIDC configuration\n"
    result += "- `helm/templates/serviceaccount.yaml.j2` - Service account\n"
    result += "- `helm/templates/rolebinding.yaml.j2` - RBAC bindings\n"
    result += "- `helm/templates/ingress.yaml.j2` - Ingress resource\n"
    result += "- `helm/templates/hpa.yaml.j2` - Horizontal pod autoscaler\n\n"

    # Utility templates
    result += "## Utility Templates\n"
    result += "- `Makefile.j2` - Build and deployment automation\n"
    result += "- `bin/configure-make.py.j2` - Makefile configuration generator (creates make.env)\n"
    result += "- `test/test_runner.py.j2` - Test runner script\n"
    result += "- `test/plugin_base.py` - Test plugin base class (as-is)\n"
    result += "- `test/test_list_resources.py` - Test resource listing (as-is)\n"
    result += "- `test/test_read_resource.py` - Test resource reading (as-is)\n"
    result += "- `test/test_list_prompts.py` - Test prompt listing (as-is)\n"

    # Note about utility scripts
    result += "\n## Utility Scripts (Separate Package)\n"
    result += "Most utility scripts are available via the mcp-base CLI:\n"
    result += "  pip install mcp-base\n"
    result += "  mcp-base --help  # Shows: add-user, create-secrets, setup-oidc, setup-rbac\n"
    result += "\n"
    result += "NOTE: bin/configure-make.py IS included in the scaffold to generate make.env\n"
    result += "for configuring the Makefile (registry, image names, namespace, etc.).\n"
    result += "For OIDC/auth setup, use: mcp-base setup-oidc\n"

    return result


async def list_patterns_impl() -> str:
    """
    List all available pattern documentation.

    Returns a list of pattern documents that explain how to
    implement various aspects of MCP servers.

    Returns:
        Formatted list of available patterns
    """
    result = "# Available Patterns\n\n"

    patterns = [
        ("generation-workflow", "MCP server generation workflow (Resources vs Tools)"),
        ("fastmcp-tools", "FastMCP tool implementation with MCPContext"),
        ("authentication", "Auth0/OIDC authentication setup"),
        ("kubernetes-integration", "Kubernetes API client patterns"),
        ("helm-chart", "Helm chart creation from helm create"),
        ("testing", "Plugin-based test framework"),
        ("deployment", "Production Kubernetes deployment"),
        ("prompt-management", "Versioned prompts with ConfigMap storage and hot-reload"),
    ]

    for name, description in patterns:
        result += f"- `{name}` - {description}\n"

    result += "\nUse `get_pattern(name)` to retrieve full documentation."

    return result


async def get_pattern_impl(name: str) -> str:
    """
    Get pattern documentation by name.

    Retrieves detailed documentation about implementation patterns
    for MCP servers.

    Args:
        name: Pattern name (e.g., "fastmcp-tools", "authentication")

    Returns:
        Full pattern documentation in Markdown format
    """
    valid_patterns = [
        "generation-workflow",
        "fastmcp-tools",
        "authentication",
        "kubernetes-integration",
        "helm-chart",
        "testing",
        "deployment",
        "prompt-management"
    ]

    if name not in valid_patterns:
        return f"Error: Unknown pattern '{name}'. Valid patterns: {', '.join(valid_patterns)}"

    pattern_path = PATTERNS_DIR / f"{name}.md"
    if not pattern_path.exists():
        return f"Error: Pattern file not found: {pattern_path}"

    return pattern_path.read_text()


async def render_template_impl(
    template_path: str,
    server_name: str,
    port: int = 4207,
    default_namespace: str = "default",
    chart_name: Optional[str] = None,
    operator_cluster_roles: Optional[str] = None,
    rbac_rules: Optional[str] = None
) -> str:
    """
    Render a single template with the given parameters.

    Use this to generate individual files from templates.
    For complete project generation, use generate_server_scaffold instead.

    Args:
        template_path: Path to template (e.g., "server/entry_point.py.j2")
        server_name: Human-readable server name (e.g., "Kubernetes Manager MCP")
        port: HTTP server port (default: 4207)
        default_namespace: Default Kubernetes namespace (default: "default")
        chart_name: Helm chart name (defaults to kebab-case of server_name)
        operator_cluster_roles: Comma-separated list of ClusterRoles to bind
        rbac_rules: JSON array of RBAC rules (for setup_rbac.py.j2)

    Returns:
        Rendered template content
    """
    # Derive names
    server_name_snake = to_snake_case(server_name)
    server_name_kebab = to_kebab_case(server_name)
    server_name_pascal = to_pascal_case(server_name)

    if chart_name is None:
        chart_name = server_name_kebab

    # Parse operator cluster roles
    cluster_roles = []
    if operator_cluster_roles:
        cluster_roles = [r.strip() for r in operator_cluster_roles.split(",")]

    # Parse RBAC rules
    rbac = []
    if rbac_rules:
        try:
            rbac = json.loads(rbac_rules)
        except json.JSONDecodeError as e:
            return f"Error parsing rbac_rules JSON: {e}"

    # Template variables
    variables = {
        "server_name": server_name,
        "server_name_snake": server_name_snake,
        "server_name_kebab": server_name_kebab,
        "server_name_pascal": server_name_pascal,
        "port": port,
        "default_namespace": default_namespace,
        "chart_name": chart_name,
        "operator_cluster_roles": cluster_roles,
        "rbac_rules": rbac,
        "verify_permission_resource": None,
    }

    try:
        template = jinja_env.get_template(template_path)
        return template.render(**variables)
    except Exception as e:
        return f"Error rendering template: {e}"


async def generate_server_scaffold_impl(
    server_name: str,
    output_description: Literal["full", "summary"] = "summary",
    port: int = 4207,
    default_namespace: str = "default",
    operator_cluster_roles: Optional[str] = None,
    include_helm: bool = True,
    include_test: bool = True
) -> Dict[str, Any]:
    """
    Generate complete MCP server project scaffold.

    Creates a full project structure with all necessary files for
    a production-ready Kubernetes MCP server. Files are stored as artifacts
    and can be retrieved individually using get_artifact.

    ========================================================================
    CRITICAL: PHASE 2 IS IMPOSSIBLE UNTIL PHASE 1 IS VERIFIED COMPLETE
    ========================================================================

    This is not advice. It is a logical dependency:
    - You cannot customize files that don't exist on disk
    - You cannot test without test-mcp.py written
    - You cannot build without Dockerfile written
    - ARTIFACTS EXPIRE - retrieve them NOW or lose them forever

    Phase 2 (customization) is UNDEFINED until Phase 1 is verified complete.
    Treat Phase 2 as impossible, not just inadvisable, until then.

    ========================================================================
    PHASE 1: SCAFFOLD RETRIEVAL (MECHANICAL - NO CREATIVITY)
    ========================================================================

    This is MECHANICAL work. Think: copy machine, not architect.

    REQUIRED STEPS (no exceptions):
    1. Call this function - note file_count in response
    2. Loop through EVERY file in the returned "files" list
    3. For EACH file: content = get_artifact(project_id, path)
    4. For EACH file: write EXACT content to ./path (current directory)
    5. VERIFY: count files on disk == file_count from response

    ARTIFACTS EXPIRE. Do not pause. Do not skip files. Complete NOW.

    ========================================================================
    PHASE 1 VERIFICATION (REQUIRED GATE)
    ========================================================================

    You CANNOT proceed until you verify:
    [ ] actual files on disk == file_count (e.g., 34 == 34)
    [ ] All files from files_list exist on disk

    If verification fails, you failed. Generate a new scaffold.

    ========================================================================
    PHASE 2: CUSTOMIZATION (IMPOSSIBLE UNTIL PHASE 1 VERIFIED)
    ========================================================================

    Only after verification passes:
    - Customize the *_tools.py file for your specific functionality
    - Add any additional dependencies to requirements.txt

    ========================================================================

    The scaffold includes:
    - src/ - Server code, tools, auth modules, test server
    - bin/ - Configuration scripts (bin/configure-make.py)
    - chart/ - Complete Helm chart with ALL templates (deployment, service, ingress, etc.)
    - test/ - Test framework with driver scripts and plugin tests
    - Dockerfile - Production container
    - Dockerfile.test - Test container (no auth, for CI/CD)
    - Makefile - Build targets including: build, build-test, push, push-test, test
    - requirements.txt

    NOTE: Most utility scripts are available via the mcp-base CLI (pip install mcp-base).
    Exception: bin/configure-make.py IS included to generate make.env for Makefile config.
    For OIDC/auth setup, use: mcp-base setup-oidc

    CRITICAL USAGE RULES:
    1. NON-DEVIATION RULE: Use MCPBase scaffold artifacts as the ONLY source of project files.
       DO NOT create alternate scaffolds or replacement files under any circumstances.
    2. ERROR HANDLING: On any tool or schema error, STOP immediately, report the full error,
       and propose tool-based recovery (e.g., list_artifacts + get_artifact).
       DO NOT attempt to work around errors by creating alternate scaffolds.
    3. PARAMETER DEFAULTS: Use default parameter values unless the user explicitly specifies otherwise.
       Do not override include_helm or include_test unless explicitly requested.

    Args:
        server_name: Human-readable server name (e.g., "Kubernetes Manager MCP")
        output_description: Deprecated - included for backward compatibility only (ignored)
        port: HTTP server port (default: 4207)
        default_namespace: Default Kubernetes namespace
        operator_cluster_roles: Comma-separated ClusterRoles to bind (e.g., "my-operator-edit,other-operator-view")
        include_helm: Include Helm chart (default: True)
        include_test: Include test framework (default: True)

    Returns:
        JSON object with project metadata, file list, and resource links.
        Use get_artifact(project_id, path) to retrieve individual files.

        Structure:
        {
            "project_id": "server-name-abc123",
            "server_name": "Server Name",
            "file_count": 37,
            "files": ["Dockerfile", "src/...", ...],
            "resource_links": [{"uri": "artifact://...", "path": "...", ...}],
            "quick_start": ["..."],
            "warnings": [],
            "truncated": false
        }

    Examples:
        - Basic: generate_server_scaffold(server_name="Kubernetes Manager MCP")
        - With roles: generate_server_scaffold(server_name="Kubernetes Manager MCP", operator_cluster_roles="my-operator-edit")
    """
    # Derive names
    server_name_snake = to_snake_case(server_name)
    server_name_kebab = to_kebab_case(server_name)
    server_name_pascal = to_pascal_case(server_name)
    chart_name = server_name_kebab

    # Parse operator cluster roles
    cluster_roles = []
    if operator_cluster_roles:
        cluster_roles = [r.strip() for r in operator_cluster_roles.split(",")]

    # Template variables
    variables = {
        "server_name": server_name,
        "server_name_snake": server_name_snake,
        "server_name_kebab": server_name_kebab,
        "server_name_pascal": server_name_pascal,
        "port": port,
        "default_namespace": default_namespace,
        "chart_name": chart_name,
        "operator_cluster_roles": cluster_roles,
        "rbac_rules": [],
        "verify_permission_resource": None,
    }

    # Files to generate
    files = {}

    # Server files - note the separated tools file pattern
    server_templates = [
        ("server/entry_point.py.j2", f"src/{server_name_snake}_server.py"),
        ("server/test_server.py.j2", f"src/{server_name_snake}_test_server.py"),
        ("server/auth_fastmcp.py.j2", "src/auth_fastmcp.py"),
        ("server/tools.py.j2", f"src/{server_name_snake}_tools.py"),
        ("server/prompt_registry.py.j2", "src/prompt_registry.py"),
    ]

    # As-is server files
    server_static = [
        ("server/auth_oidc.py", "src/auth_oidc.py"),
        ("server/mcp_context.py", "src/mcp_context.py"),
        ("server/user_hash.py", "src/user_hash.py"),
    ]

    # Container files
    container_templates = [
        ("container/Dockerfile.j2", "Dockerfile"),
        ("container/Dockerfile.test.j2", "Dockerfile.test"),
    ]

    container_static = [
        ("container/requirements.txt", "requirements.txt"),
    ]

    # Makefile
    makefile = [
        ("Makefile.j2", "Makefile"),
    ]

    # Bin scripts (coordinate with Dockerfile/Makefile)
    bin_templates = [
        ("bin/configure-make.py.j2", "bin/configure-make.py"),
    ]

    # Process template files
    for template_path, output_path in server_templates + container_templates + makefile + bin_templates:
        try:
            template = jinja_env.get_template(template_path)
            files[output_path] = template.render(**variables)
        except Exception as e:
            files[output_path] = f"# Error rendering: {e}"

    # Process static files
    for template_path, output_path in server_static + container_static:
        static_path = TEMPLATES_DIR / template_path
        if static_path.exists():
            files[output_path] = static_path.read_text()

    # Helm chart
    if include_helm:
        helm_templates = [
            ("helm/Chart.yaml.j2", "chart/Chart.yaml"),
            ("helm/values.yaml.j2", "chart/values.yaml"),
            ("helm/templates/_helpers.tpl.j2", "chart/templates/_helpers.tpl"),
            ("helm/templates/deployment.yaml.j2", "chart/templates/deployment.yaml"),
            ("helm/templates/service.yaml.j2", "chart/templates/service.yaml"),
            ("helm/templates/configmap.yaml.j2", "chart/templates/configmap.yaml"),
            ("helm/templates/prompts-configmap.yaml.j2", "chart/templates/prompts-configmap.yaml"),
            ("helm/templates/serviceaccount.yaml.j2", "chart/templates/serviceaccount.yaml"),
            ("helm/templates/rolebinding.yaml.j2", "chart/templates/rolebinding.yaml"),
            ("helm/templates/ingress.yaml.j2", "chart/templates/ingress.yaml"),
            ("helm/templates/hpa.yaml.j2", "chart/templates/hpa.yaml"),
        ]

        for template_path, output_path in helm_templates:
            try:
                template = jinja_env.get_template(template_path)
                files[output_path] = template.render(**variables)
            except Exception as e:
                files[output_path] = f"# Error rendering: {e}"

        files["chart/.helmignore"] = """# Patterns to ignore when building packages.
.git/
.gitignore
.DS_Store
"""

        files["chart/templates/NOTES.txt"] = f"""{{{{- $fullName := include "{chart_name}.fullname" . -}}}}
1. Get the application URL by running these commands:
{{{{- if .Values.ingress.enabled }}}}
  http{{{{- if .Values.ingress.tls.enabled }}}}s{{{{- end }}}}://{{{{ .Values.ingress.host }}}}
{{{{- else if contains "NodePort" .Values.service.type }}}}
  export NODE_PORT=$(kubectl get --namespace {{{{ .Release.Namespace }}}} -o jsonpath="{{{{.spec.ports[0].nodePort}}}}" services {{{{ $fullName }}}})
  export NODE_IP=$(kubectl get nodes --namespace {{{{ .Release.Namespace }}}} -o jsonpath="{{{{.items[0].status.addresses[0].address}}}}")
  echo http://$NODE_IP:$NODE_PORT
{{{{- else if contains "ClusterIP" .Values.service.type }}}}
  kubectl --namespace {{{{ .Release.Namespace }}}} port-forward svc/{{{{ $fullName }}}} {port}:{port}
  echo "Visit http://127.0.0.1:{port}/mcp"
{{{{- end }}}}
"""

    # Test framework
    if include_test:
        test_templates = [
            ("test/test_runner.py.j2", "test/test-mcp.py"),
        ]

        test_static = [
            ("test/plugin_base.py", "test/plugins/__init__.py"),
            ("test/get_user_token.py", "test/get-user-token.py"),
            ("test/auth_proxy.py", "test/mcp-auth-proxy.py"),
            ("test/test_list_resources.py", "test/plugins/test_list_resources.py"),
            ("test/test_read_resource.py", "test/plugins/test_read_resource.py"),
            ("test/test_list_prompts.py", "test/plugins/test_list_prompts.py"),
        ]

        for template_path, output_path in test_templates:
            try:
                template = jinja_env.get_template(template_path)
                files[output_path] = template.render(**variables)
            except Exception as e:
                files[output_path] = f"# Error rendering: {e}"

        for template_path, output_path in test_static:
            static_path = TEMPLATES_DIR / template_path
            if static_path.exists():
                files[output_path] = static_path.read_text()

        # Example test plugin
        files["test/plugins/test_example.py"] = f'''"""
Example test plugin for {server_name}.

Copy this file and modify for your own tools.
"""
from plugins import TestPlugin, TestResult
import time


class TestExampleTool(TestPlugin):
    """Example test for a tool."""

    tool_name = "example_tool"
    description = "Tests the example tool"
    depends_on = []
    run_after = []

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            # Call your tool here
            # result = await session.call_tool("your_tool", arguments={{}})

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message="Example test passed (implement your test here)",
                duration_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="Test failed",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
'''

    # NOTE: Utility scripts (add-user, setup-oidc, setup-rbac, etc.) are NOT included in the
    # scaffold. They are available via the mcp-base CLI (pip install mcp-base) to avoid context
    # bloat - these large utility scripts don't need customization and can be run via mcp-base.

    # Generate unique project ID for artifact storage
    project_id = f"{server_name_kebab}-{uuid.uuid4().hex[:8]}"

    # Store all files as artifacts
    for path, content in files.items():
        mime_type = get_mime_type_for_path(path)
        artifact_store.store(
            project_id=project_id,
            path=path,
            content=content,
            mime_type=mime_type,
            description=f"Generated file for {server_name}"
        )

    # Build resource links for all files (always)
    resource_links = []
    for path in sorted(files.keys()):
        mime_type = get_mime_type_for_path(path)
        filename = path.split("/")[-1]
        resource_links.append({
            "uri": f"artifact://{project_id}/{path}",
            "path": path,
            "name": filename,
            "mimeType": mime_type
        })

    # Always return a consistent JSON object structure
    result = {
        "project_id": project_id,
        "server_name": server_name,
        "server_name_snake": server_name_snake,
        "server_name_kebab": server_name_kebab,
        "file_count": len(files),
        "files": sorted(files.keys()),
        "resource_links": resource_links,
        "quick_start": [
            "======== PHASE 2 IS IMPOSSIBLE UNTIL PHASE 1 IS VERIFIED ========",
            "This is not advice. It is a logical dependency.",
            "You cannot customize files that don't exist. ARTIFACTS EXPIRE.",
            "",
            "======== PHASE 1: RETRIEVE ALL FILES NOW ========",
            f"STEP 1: Loop through ALL {len(files)} files in 'files' list",
            f"STEP 2: For EACH: content = get_artifact('{project_id}', path)",
            "STEP 3: For EACH: write EXACT content to ./path",
            f"STEP 4: VERIFY: count files on disk == {len(files)}",
            "STEP 5: Make bin scripts executable: chmod +x bin/*",
            "",
            "Do not pause. Do not skip. Complete NOW or artifacts expire.",
            "",
            "======== PHASE 2: CUSTOMIZATION (IMPOSSIBLE UNTIL VERIFIED) ========",
            f"Only after {len(files)} files verified on disk:",
            f"  - Customize src/{server_name_snake}_tools.py",
            f"  - Test: python src/{server_name_snake}_server.py --port {port}",
            "  - Configure: python bin/configure-make.py  # Then: mcp-base setup-oidc",
            "  - Deploy: make build && make push && make helm-install"
        ],
        "warnings": [],
        "truncated": False
    }

    # Add a summary field for backward compatibility if requested
    if output_description == "summary":
        result["summary"] = f"Generated {len(files)} files for {server_name}. Use get_artifact(project_id, path) to retrieve files."

    return result


# ============================================================================
# Resource Registration
# ============================================================================

def register_resources(mcp):
    """
    Register all resources with the MCP server instance.

    This function is called from the server entry points to register
    all resource implementations with the FastMCP instance.

    Args:
        mcp: FastMCP server instance
    """

    # Template resources
    @mcp.resource("template://server/entry_point.py")
    def get_entry_point_template() -> str:
        """Server entry point template (HTTP transport)."""
        template_path = TEMPLATES_DIR / "server" / "entry_point.py.j2"
        return template_path.read_text()

    @mcp.resource("template://server/auth_fastmcp.py")
    def get_auth_fastmcp_template() -> str:
        """FastMCP Auth0 provider configuration template."""
        template_path = TEMPLATES_DIR / "server" / "auth_fastmcp.py.j2"
        return template_path.read_text()

    @mcp.resource("template://server/auth_oidc.py")
    def get_auth_oidc() -> str:
        """Generic OIDC authentication provider (as-is)."""
        template_path = TEMPLATES_DIR / "server" / "auth_oidc.py"
        return template_path.read_text()

    @mcp.resource("template://server/mcp_context.py")
    def get_mcp_context() -> str:
        """MCPContext class and with_mcp_context decorator (as-is)."""
        template_path = TEMPLATES_DIR / "server" / "mcp_context.py"
        return template_path.read_text()

    @mcp.resource("template://server/user_hash.py")
    def get_user_hash() -> str:
        """User ID generation utilities (as-is)."""
        template_path = TEMPLATES_DIR / "server" / "user_hash.py"
        return template_path.read_text()

    @mcp.resource("template://server/tools.py")
    def get_tools_template() -> str:
        """Tool implementation skeleton template."""
        template_path = TEMPLATES_DIR / "server" / "tools.py.j2"
        return template_path.read_text()

    @mcp.resource("template://server/prompt_registry.py")
    def get_prompt_registry_template() -> str:
        """Versioned prompt management with hot-reload template."""
        template_path = TEMPLATES_DIR / "server" / "prompt_registry.py.j2"
        return template_path.read_text()

    @mcp.resource("template://container/Dockerfile")
    def get_dockerfile_template() -> str:
        """Container Dockerfile template."""
        template_path = TEMPLATES_DIR / "container" / "Dockerfile.j2"
        return template_path.read_text()

    @mcp.resource("template://container/requirements.txt")
    def get_requirements() -> str:
        """Python requirements.txt (as-is)."""
        template_path = TEMPLATES_DIR / "container" / "requirements.txt"
        return template_path.read_text()

    @mcp.resource("template://helm/Chart.yaml")
    def get_chart_yaml_template() -> str:
        """Helm Chart.yaml template with Redis dependency."""
        template_path = TEMPLATES_DIR / "helm" / "Chart.yaml.j2"
        return template_path.read_text()

    @mcp.resource("template://helm/values.yaml")
    def get_values_yaml_template() -> str:
        """Helm values.yaml template."""
        template_path = TEMPLATES_DIR / "helm" / "values.yaml.j2"
        return template_path.read_text()

    @mcp.resource("template://Makefile")
    def get_makefile_template() -> str:
        """Build automation Makefile template."""
        template_path = TEMPLATES_DIR / "Makefile.j2"
        return template_path.read_text()

    # Pattern resources
    @mcp.resource("pattern://generation-workflow")
    def get_generation_workflow_pattern() -> str:
        """Pattern documentation for MCP server generation workflow (Resources vs Tools)."""
        pattern_path = PATTERNS_DIR / "generation-workflow.md"
        return pattern_path.read_text()

    @mcp.resource("pattern://fastmcp-tools")
    def get_fastmcp_tools_pattern() -> str:
        """Pattern documentation for implementing FastMCP tools."""
        pattern_path = PATTERNS_DIR / "fastmcp-tools.md"
        return pattern_path.read_text()

    @mcp.resource("pattern://authentication")
    def get_authentication_pattern() -> str:
        """Pattern documentation for Auth0/OIDC authentication."""
        pattern_path = PATTERNS_DIR / "authentication.md"
        return pattern_path.read_text()

    @mcp.resource("pattern://kubernetes-integration")
    def get_kubernetes_pattern() -> str:
        """Pattern documentation for Kubernetes API integration."""
        pattern_path = PATTERNS_DIR / "kubernetes-integration.md"
        return pattern_path.read_text()

    @mcp.resource("pattern://helm-chart")
    def get_helm_chart_pattern() -> str:
        """Pattern documentation for Helm chart creation."""
        pattern_path = PATTERNS_DIR / "helm-chart.md"
        return pattern_path.read_text()

    @mcp.resource("pattern://testing")
    def get_testing_pattern() -> str:
        """Pattern documentation for testing MCP servers."""
        pattern_path = PATTERNS_DIR / "testing.md"
        return pattern_path.read_text()

    @mcp.resource("pattern://deployment")
    def get_deployment_pattern() -> str:
        """Pattern documentation for production deployment."""
        pattern_path = PATTERNS_DIR / "deployment.md"
        return pattern_path.read_text()

    @mcp.resource("pattern://prompt-management")
    def get_prompt_management_pattern() -> str:
        """Pattern documentation for versioned prompts with ConfigMap storage and hot-reload."""
        pattern_path = PATTERNS_DIR / "prompt-management.md"
        return pattern_path.read_text()

    @mcp.resource("pattern://architecture")
    def get_architecture_pattern() -> str:
        """Architecture documentation for MCP server design patterns and pitfalls."""
        architecture_path = BASE_DIR / "ARCHITECTURE.md"
        return architecture_path.read_text()

    # Dynamic artifact resource - list artifacts in a project
    @mcp.resource("artifact://{project_id}")
    def list_project_artifacts(project_id: str) -> str:
        """
        List all artifacts in a generated project.

        Args:
            project_id: The project identifier (e.g., "my-server-abc12345")

        Returns:
            JSON list of artifact paths and URIs
        """
        artifacts = artifact_store.list_project(project_id)
        if not artifacts:
            return f"Error: No artifacts found for project: {project_id}"
        return json.dumps([{"path": path, "uri": uri} for path, uri in artifacts], indent=2)


# ============================================================================
# Tool Registration
# ============================================================================

def register_tools(mcp):
    """
    Register all tools with the MCP server instance.

    This function is called from the main server entry point to register
    all tool implementations with the FastMCP instance.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(name="list_templates")
    async def list_templates() -> str:
        """List all available templates for MCP server construction."""
        return await list_templates_impl()

    @mcp.tool(name="list_patterns")
    async def list_patterns() -> str:
        """List all available pattern documentation."""
        return await list_patterns_impl()

    @mcp.tool(name="get_pattern")
    async def get_pattern(name: str) -> str:
        """Get pattern documentation by name."""
        return await get_pattern_impl(name)

    @mcp.tool(name="render_template")
    async def render_template(
        template_path: str,
        server_name: str,
        port: int = 4207,
        default_namespace: str = "default",
        chart_name: Optional[str] = None,
        operator_cluster_roles: Optional[str] = None,
        rbac_rules: Optional[str] = None
    ) -> str:
        """Render a single template with the given parameters."""
        return await render_template_impl(
            template_path=template_path,
            server_name=server_name,
            port=port,
            default_namespace=default_namespace,
            chart_name=chart_name,
            operator_cluster_roles=operator_cluster_roles,
            rbac_rules=rbac_rules
        )

    @mcp.tool(name="generate_server_scaffold")
    async def generate_server_scaffold(
        server_name: str,
        output_description: Literal["full", "summary"] = "summary",
        port: int = 4207,
        default_namespace: str = "default",
        operator_cluster_roles: Optional[str] = None,
        include_helm: bool = True,
        include_test: bool = True
    ) -> Dict[str, Any]:
        """
        Generate complete MCP server project scaffold.

        Returns a JSON object with project metadata and file references.
        Use get_artifact(project_id, path) to retrieve individual files.

        NOTE: Utility scripts are NOT included. They are available via the mcp-base CLI:
        pip install mcp-base && mcp-base --help

        Returns:
            JSON object containing:
            - project_id: Unique identifier for retrieving artifacts
            - files: List of all generated file paths
            - quick_start: Steps to get started
        """
        return await generate_server_scaffold_impl(
            server_name=server_name,
            output_description=output_description,
            port=port,
            default_namespace=default_namespace,
            operator_cluster_roles=operator_cluster_roles,
            include_helm=include_helm,
            include_test=include_test
        )

    @mcp.tool(name="get_artifact")
    async def get_artifact(project_id: str, path: str) -> str:
        """
        Retrieve a generated artifact file by project ID and path.

        After calling generate_server_scaffold, use this tool to retrieve
        individual generated files. This allows fetching one file at a time
        instead of all files at once, reducing context usage.

        CRITICAL: If this tool returns an error, DO NOT create replacement files.
        Instead, use list_artifacts to see available files, or report the error
        and ask the user for guidance.

        Args:
            project_id: The project identifier returned by generate_server_scaffold
                        (e.g., "my-server-abc12345")
            path: The file path within the project (e.g., "src/my_server.py",
                  "Makefile", "chart/values.yaml")

        Returns:
            File content as text, or error message if not found
        """
        artifact = artifact_store.get(project_id, path)
        if artifact is None:
            # List available files to help the user
            available = artifact_store.list_project(project_id)
            if not available:
                return f"Error: Project '{project_id}' not found. No artifacts stored."
            paths = [p for p, _ in available]
            return f"Error: Artifact '{path}' not found in project '{project_id}'.\n\nAvailable files:\n" + "\n".join(f"  - {p}" for p in paths[:20])
        return artifact.content

    @mcp.tool(name="list_artifacts")
    async def list_artifacts(project_id: str) -> str:
        """
        List all generated artifacts in a project.

        Use this after generate_server_scaffold to see all available files,
        then use get_artifact to retrieve specific files.

        CRITICAL: This is the authoritative source for project files. Always use
        the official artifact list - DO NOT create alternate file lists or replacement
        scaffolds.

        Args:
            project_id: The project identifier returned by generate_server_scaffold

        Returns:
            JSON list of available artifact paths
        """
        artifacts = artifact_store.list_project(project_id)
        if not artifacts:
            all_projects = artifact_store.list_all_projects()
            if all_projects:
                return f"Error: Project '{project_id}' not found.\n\nAvailable projects:\n" + "\n".join(f"  - {p}" for p in all_projects)
            return f"Error: No artifacts stored. Call generate_server_scaffold first."
        return json.dumps({
            "project_id": project_id,
            "file_count": len(artifacts),
            "files": [path for path, _ in artifacts]
        }, indent=2)

