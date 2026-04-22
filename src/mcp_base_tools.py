"""
MCP Base Server - Tool Implementations

This module contains all tool implementations for the mcp-base server.
Tools are decorated with @mcp.tool() and follow the standard pattern.

The mcp instance is passed in via register_tools() to avoid circular imports.
"""

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Optional, Literal, List, Dict, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from fastmcp.resources import TextResource

from artifact_store import artifact_store, get_mime_type_for_path

logger = logging.getLogger(__name__)

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
    include_test: bool = True,
    auth_type: Literal["auth0", "keycloak", "oidc"] = "auth0"
) -> Dict[str, Any]:
    """
    Generate complete MCP server project scaffold.

    Creates a full project structure with all necessary files for
    a production-ready Kubernetes MCP server. Files are stored as artifacts
    keyed by project_id and exposed via TWO equivalent retrieval paths:

      1. Tool — `read_scaffold_artifact(project_id, path)` — always works,
         regardless of whether the client's aggregator forwards resources.
      2. Resource — `resources/read("scaffold://{project_id}/{path}")` —
         each artifact is registered as a concrete MCP resource so it
         appears in `resources/list` and resolves directly. A URI-template
         handler is also registered as a fallback.

    Either path returns identical bytes. Pick whichever fits your client.

    ========================================================================
    CRITICAL ARTIFACT RETRIEVAL GATE
    ========================================================================

    Artifact retrieval is a HARD GATE. The scaffold is valid only if each
    file on disk was written from the EXACT content returned by
    `read_scaffold_artifact` for that file's path.

    If ANY artifact retrieval fails, STOP IMMEDIATELY. Do NOT:
      - Reconstruct files from memory
      - Render templates as a substitute (`render_template` is NOT a fallback)
      - Create placeholder files
      - Infer missing contents from filenames
      - Continue to Phase 2 (customization)
      - Create SCAFFOLD_INVENTORY.md as if retrieval succeeded

    Instead, create SCAFFOLD_RETRIEVAL_FAILURE.md documenting the failure
    (template included in the returned `quick_start` field).

    Phase 2 (customization) is UNDEFINED until Phase 1 is verified complete.
    Treat Phase 2 as impossible, not just inadvisable, until then.

    ========================================================================
    PHASE 1: RETRIEVE ALL ARTIFACTS (MECHANICAL — NO CREATIVITY)
    ========================================================================

    This is MECHANICAL work. Think: copy machine, not architect.

    REQUIRED STEPS:
    1. Call this function — note `file_count`, `files`, and
       `scaffold_resources` in the response.
    2. Loop through EVERY path in `files`. For each path, use EITHER:
         (A) content = call_tool('read_scaffold_artifact', {
                 'project_id': <project_id>, 'path': <path>
             })
         (B) content = read_resource('scaffold://<project_id>/<path>')
       Both return identical bytes; pick whichever your client supports.
    3. On success: write the EXACT returned bytes to ./<path>.
    4. On failure: record the path and error — do NOT substitute anything.

    After the loop:
    - If any failures: STOP. Create SCAFFOLD_RETRIEVAL_FAILURE.md and halt.
    - If all succeeded: proceed to Phase 1 verification.

    ========================================================================
    PHASE 1 VERIFICATION (REQUIRED GATE)
    ========================================================================

    You CANNOT proceed until you verify:
    [ ] Retrieved exactly file_count files (no skips)
    [ ] Each file written with the EXACT bytes returned by the API
    [ ] No placeholders, template renders, or reconstructions
    [ ] Every path in `files` exists on disk

    Only after all boxes are checked: create SCAFFOLD_INVENTORY.md.

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
       and propose recovery by retrying `read_scaffold_artifact` for the affected path.
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
        auth_type: Authentication type (default: "auth0"):
                   - "auth0": FastMCP Auth0Provider OAuth proxy (issues MCP tokens, Redis session storage)
                   - "keycloak": FastMCP KeycloakAuthProvider (DCR-based, requires Keycloak >= 26.6.0
                     and fastmcp >= 3.2.4; no client_secret/JWT signing key/Redis required)
                   - "oidc": Generic OIDC middleware for other IdPs (Dex, Okta, etc.)

    Returns:
        JSON object with project metadata, file list, and scaffold_resources dict.
        Retrieve individual files via either:
          - `read_scaffold_artifact(project_id, path)` (tool), or
          - `resources/read("scaffold://{project_id}/{path}")` (MCP resource).

        Structure:
        {
            "project_id": "server-name-abc123",
            "server_name": "Server Name",
            "file_count": 37,
            "files": ["Dockerfile", "src/...", ...],
            "scaffold_resources": {"<path>": "scaffold://<id>/<path>", ...},
            "resource_links": [{"path": "...", "uri": "...", "mime_type": "..."}, ...],
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
        "auth_type": auth_type,  # "auth0", "keycloak", or "oidc"
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
            ("helm/templates/NOTES.txt.j2", "chart/templates/NOTES.txt"),
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

    # Always return a consistent JSON object structure
    result = {
        "project_id": project_id,
        "server_name": server_name,
        "server_name_snake": server_name_snake,
        "server_name_kebab": server_name_kebab,
        "file_count": len(files),
        "files": sorted(files.keys()),
        "quick_start": [
            "========================================================================",
            "CRITICAL ARTIFACT RETRIEVAL GATE",
            "========================================================================",
            "",
            "Before writing any scaffold files, you MUST retrieve every scaffold",
            "artifact via the `read_scaffold_artifact` tool. Retrieval is a HARD GATE.",
            "",
            "INVARIANT: The scaffold is valid only if each file on disk was written",
            "from the EXACT content returned by read_scaffold_artifact for that",
            "file's path. If this invariant cannot be satisfied, the correct",
            "output is a FAILURE REPORT — not a partial scaffold.",
            "",
            "If ANY artifact retrieval fails, STOP IMMEDIATELY. Do NOT:",
            "  - Reconstruct files from memory",
            "  - Render templates as a substitute (render_template is NOT a fallback)",
            "  - Create placeholder files",
            "  - Infer missing contents from filenames",
            "  - Continue to customization",
            "  - Create SCAFFOLD_INVENTORY.md as if retrieval succeeded",
            "",
            "Instead, create SCAFFOLD_RETRIEVAL_FAILURE.md (template below).",
            "",
            "========================================================================",
            "PHASE 1: RETRIEVE ALL ARTIFACTS (MECHANICAL — NO CREATIVITY)",
            "========================================================================",
            "",
            "Retrieval API — pick EITHER path (both return identical bytes):",
            "",
            "  (A) Tool call (always works):",
            f"      content = call_tool('read_scaffold_artifact', {{",
            f"          'project_id': '{project_id}',",
            f"          'path': '<file path from files list>'",
            f"      }})",
            "",
            "  (B) MCP resource (for clients that support resources/read):",
            f"      content = read_resource('scaffold://{project_id}/<path>')",
            "",
            f"Loop through ALL {len(files)} paths in the 'files' field. For each:",
            "  1. Retrieve via (A) or (B)",
            "  2. On success: write the returned content to disk at ./<path>",
            "  3. On failure: add the path to a retrieval_failures list — do NOT",
            "     write anything for that file, do NOT substitute template content",
            "",
            "After the loop:",
            "  - If retrieval_failures is empty: proceed to Phase 1 verification",
            "  - If retrieval_failures is non-empty: STOP. Create",
            "    SCAFFOLD_RETRIEVAL_FAILURE.md and halt. Do not continue.",
            "",
            "========================================================================",
            "PHASE 1 VERIFICATION (REQUIRED GATE)",
            "========================================================================",
            "",
            f"[ ] Retrieved exactly {len(files)} of {len(files)} expected files",
            "[ ] Each file written to disk with the EXACT bytes returned by the tool",
            "[ ] No placeholders, no template-rendered substitutes, no reconstructions",
            "[ ] No files skipped",
            "",
            "Only after all four boxes are checked: create SCAFFOLD_INVENTORY.md",
            "with one entry per file (path, line count, size in bytes, first 5",
            "function/class names). Then chmod +x bin/*.",
            "",
            "========================================================================",
            "SCAFFOLD_RETRIEVAL_FAILURE.md TEMPLATE (use on any retrieval error)",
            "========================================================================",
            "",
            "# Scaffold Retrieval Failure",
            "",
            f"- Project ID: {project_id}",
            f"- Expected files: {len(files)}",
            "- Retrieved files: <count>",
            "- Failed files: <count>",
            "- Files written to disk: none",
            "",
            "## Failed Artifact Reads",
            "",
            "| Path | Error |",
            "| --- | --- |",
            "| <path> | <exact error message> |",
            "",
            "## Conclusion",
            "",
            "Scaffold generation returned a manifest, but scaffold artifacts were",
            "not retrievable via read_scaffold_artifact. No scaffold files were",
            "written because doing so would violate the exact-artifact invariant.",
            "",
            "## Suggested Next Step",
            "",
            "Verify that the MCP server exposes either:",
            "  - read_scaffold_artifact as a tool in the same session, OR",
            "  - scaffold://{project_id}/{path} as a concrete MCP resource",
            "",
            "and that the project_id has not expired. Retry generation if the",
            "server was restarted between calls.",
            "",
            "========================================================================",
            "PHASE 2: CUSTOMIZE (ONLY AFTER PHASE 1 VERIFIED COMPLETE)",
            "========================================================================",
            "",
            f"  - Customize src/{server_name_snake}_tools.py",
            f"  - Test: python src/{server_name_snake}_server.py --port {port}",
            "  - Configure: python bin/configure-make.py  # Then: mcp-base setup-oidc",
            "  - Deploy: make build && make push && make helm-install",
            "",
            "Phase 2 is UNDEFINED until Phase 1 verification succeeded. A failed",
            "Phase 1 means the correct output is SCAFFOLD_RETRIEVAL_FAILURE.md,",
            "not customized code."
        ],
        "warnings": [],
        "truncated": False
    }

    # Add a summary field for backward compatibility if requested
    if output_description == "summary":
        result["summary"] = (
            f"Generated {len(files)} files for {server_name}. "
            f"Retrieve each file via read_scaffold_artifact(project_id='{project_id}', path=<path>) "
            f"or resources/read('scaffold://{project_id}/<path>') — both return identical bytes. "
            f"If retrieval fails, STOP and create SCAFFOLD_RETRIEVAL_FAILURE.md — "
            f"do not render templates or reconstruct files."
        )

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

    # Scaffold artifact resources (URI-template fallbacks).
    #
    # Each artifact is ALSO registered as a concrete TextResource from the
    # `generate_server_scaffold` tool wrapper (see register_tools). The
    # concrete registration is what surfaces artifacts in `resources/list`
    # and makes `resources/read(scaffold://{project_id}/{path})` resolvable
    # through MCP aggregators that do not forward URI templates.
    #
    # The URI-template handlers below are kept as a fallback for clients and
    # aggregators that *do* support RFC 6570 resource templates — they let
    # a client resolve a scaffold URI even if the concrete registration has
    # been pruned (e.g. after a server restart that dropped the in-memory
    # FastMCP registry but where the artifact_store is still populated).

    @mcp.resource("scaffold://{project_id}/{path*}")
    def read_scaffold_resource(project_id: str, path: str) -> str:
        """
        Read a scaffold artifact by its scaffold:// URI.

        This is the URI-template fallback path. The preferred retrieval
        paths are:
          - Tool: `read_scaffold_artifact(project_id, path)` — always works
          - Concrete resource: `resources/read("scaffold://<id>/<path>")` —
            works on aggregators that surface concrete resources
        """
        artifact = artifact_store.get(project_id, path)
        if artifact is None:
            raise ValueError(
                f"Scaffold artifact not found: scaffold://{project_id}/{path}. "
                f"Call list_artifacts('{project_id}') to see available paths, "
                f"or regenerate with generate_server_scaffold if the project expired."
            )
        return artifact.content

    @mcp.resource("artifact://{project_id}/{path*}")
    def read_artifact_resource(project_id: str, path: str) -> str:
        """
        Read a scaffold artifact by its artifact:// URI (alias for scaffold://).

        The artifact_store uses artifact:// URIs internally; this handler
        accepts them so older clients that captured artifact:// URIs still
        resolve.
        """
        artifact = artifact_store.get(project_id, path)
        if artifact is None:
            raise ValueError(
                f"Scaffold artifact not found: artifact://{project_id}/{path}"
            )
        return artifact.content


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
        include_test: bool = True,
        auth_type: Literal["auth0", "keycloak", "oidc"] = "auth0"
    ) -> Dict[str, Any]:
        """
        Generate complete MCP server project scaffold.

        Returns a JSON object with project metadata and a list of file paths.
        Each file is registered as an MCP resource at
        `scaffold://{project_id}/{path}` AND is retrievable via the
        `read_scaffold_artifact(project_id, path)` tool. Use whichever
        retrieval path your client supports.

        NOTE: Utility scripts are NOT included. They are available via the mcp-base CLI:
        pip install mcp-base && mcp-base --help

        Args:
            auth_type: Authentication type (default: "auth0"):
                       - "auth0": FastMCP Auth0Provider OAuth proxy
                       - "keycloak": FastMCP KeycloakAuthProvider (DCR-based, requires
                         Keycloak >= 26.6.0 and fastmcp >= 3.2.4)
                       - "oidc": Generic OIDC middleware for other IdPs (Dex, Okta, etc.)

        Returns:
            JSON object containing:
            - project_id: Unique identifier for artifacts
            - files: List of all generated file paths
            - scaffold_resources: Mapping of path -> scaffold:// resource URI
            - resource_links: List of {path, uri, mime_type} for each artifact
            - quick_start: Steps to get started
        """
        result = await generate_server_scaffold_impl(
            server_name=server_name,
            output_description=output_description,
            port=port,
            default_namespace=default_namespace,
            operator_cluster_roles=operator_cluster_roles,
            include_helm=include_helm,
            include_test=include_test,
            auth_type=auth_type
        )

        # Register each artifact as a concrete MCP resource so it appears in
        # `resources/list` and is directly addressable via `resources/read`.
        # This is the primary fix for clients/aggregators that don't forward
        # URI templates — the URI-template handler in register_resources
        # remains as a fallback.
        project_id = result["project_id"]
        scaffold_resources: Dict[str, str] = {}
        resource_links: List[Dict[str, str]] = []

        for path, _artifact_uri in artifact_store.list_project(project_id):
            artifact = artifact_store.get(project_id, path)
            if artifact is None:
                continue
            scaffold_uri = f"scaffold://{project_id}/{path}"
            try:
                mcp.add_resource(TextResource(
                    uri=scaffold_uri,
                    name=f"scaffold:{project_id}:{path}",
                    text=artifact.content,
                    mime_type=artifact.mime_type,
                    description=f"Scaffold file {path} for project {project_id}",
                ))
            except Exception as e:
                logger.warning(
                    f"Failed to register concrete scaffold resource {scaffold_uri}: {e}"
                )
            scaffold_resources[path] = scaffold_uri
            resource_links.append({
                "path": path,
                "uri": scaffold_uri,
                "mime_type": artifact.mime_type,
            })

        result["scaffold_resources"] = scaffold_resources
        result["resource_links"] = resource_links
        return result

    @mcp.tool(name="list_artifacts")
    async def list_artifacts(project_id: str) -> str:
        """
        List all generated artifacts in a project.

        Use this after generate_server_scaffold to see all available files,
        then use read_scaffold_artifact to retrieve individual file content.

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
            "files": [path for path, _ in artifacts],
            "retrieval_api": {
                "primary_tool": "read_scaffold_artifact(project_id, path)",
                "primary_resource_uri": f"scaffold://{project_id}/<path>",
                "notes": (
                    "Every artifact is registered as a concrete MCP resource at "
                    "scaffold://{project_id}/{path} AND is retrievable via the "
                    "read_scaffold_artifact tool. Use whichever path your client "
                    "supports; both return identical bytes."
                ),
                "gate": (
                    "If any retrieval fails, STOP. Create "
                    "SCAFFOLD_RETRIEVAL_FAILURE.md. Do NOT render templates or "
                    "reconstruct files as a substitute."
                ),
            },
        }, indent=2)

    @mcp.tool(name="read_scaffold_artifact")
    async def read_scaffold_artifact(project_id: str, path: str) -> str:
        """
        Read the exact content of a single scaffold artifact.

        This is the tool-based retrieval path. The same content is also
        available as an MCP resource at `scaffold://{project_id}/{path}` —
        each artifact is registered concretely at generation time, so
        clients that support `resources/read` can use that path instead.
        Both paths return identical bytes.

        RETRIEVAL GATE (see generate_server_scaffold instructions):
        If retrieval fails for ANY expected file — via either path — STOP.
        Do not reconstruct the file from memory, do not render templates as
        a substitute, do not create a placeholder. Produce a
        SCAFFOLD_RETRIEVAL_FAILURE.md report instead, per the failure
        template in the tool's instructions.

        Args:
            project_id: The project identifier returned by generate_server_scaffold
            path: File path within the project (e.g., "src/my_server.py").
                  Must match a path from the scaffold's `files` list exactly.

        Returns:
            Exact file content as stored at scaffold generation time.

        Raises:
            ValueError: If the project or file is not found. Treat this as a
            retrieval failure — do NOT fall back to template rendering.
        """
        artifact = artifact_store.get(project_id, path)
        if artifact is None:
            available = artifact_store.list_project(project_id)
            if not available:
                all_projects = artifact_store.list_all_projects()
                hint = (
                    f"\n\nAvailable projects:\n" + "\n".join(f"  - {p}" for p in all_projects)
                    if all_projects else
                    "\n\nNo scaffold projects are currently stored. Call generate_server_scaffold first."
                )
                raise ValueError(
                    f"Project '{project_id}' not found. It may have expired.{hint}"
                )
            available_paths = [p for p, _ in available]
            raise ValueError(
                f"File '{path}' not found in project '{project_id}'.\n"
                f"Available files ({len(available_paths)}):\n"
                + "\n".join(f"  - {p}" for p in available_paths[:20])
                + ("\n  ..." if len(available_paths) > 20 else "")
            )
        return artifact.content
