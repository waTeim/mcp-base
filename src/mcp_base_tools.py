"""
MCP Base Server - Tool Implementations

This module contains all tool implementations for the mcp-base server.
Tools are decorated with @mcp.tool() and follow the standard pattern.

The mcp instance is passed in via register_tools() to avoid circular imports.
"""

import ast
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Optional, Literal, List, Dict, Any, Tuple

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
# Artifact Metadata Inference
# ============================================================================
#
# Role/relevance/summary/notes are inferred from the generated file's output
# path. The inference layer keeps the metadata tools compact — clients can
# look at role+relevance to decide which artifacts to inspect locally before
# customizing, without pulling any file bytes into model context.

# Patterns are evaluated in order; the first match wins. Project-specific
# snake_case tokens in output paths are matched with a loose regex so the
# same rule covers any server name.
_PY_NAME = r"[a-z][a-z0-9_]*"

_ROLE_RULES = [
    # (regex pattern against output path, role metadata dict)
    (re.compile(rf"^src/{_PY_NAME}_test_server\.py$"), {
        "role": "test_server",
        "customization_relevance": "low",
        "summary": "OIDC test server entrypoint used for automated tests.",
        "customization_notes": [
            "Rarely customized. Mirrors the production server but accepts OIDC JWTs directly."
        ],
        "verification_notes": [
            "Run against --no-auth for headless CI when needed.",
        ],
    }),
    (re.compile(rf"^src/{_PY_NAME}_server\.py$"), {
        "role": "server_entrypoint",
        "customization_relevance": "medium",
        "summary": "FastMCP production server entrypoint (transport, auth, route wiring).",
        "customization_notes": [
            "Wire additional tool/resource modules via register_*() calls.",
            "Keep auth middleware initialization aligned with auth_fastmcp.py.",
        ],
        "verification_notes": [
            "python src/<snake>_server.py --port <port> and curl /healthz.",
        ],
    }),
    (re.compile(rf"^src/{_PY_NAME}_tools\.py$"), {
        "role": "tools_module",
        "customization_relevance": "high",
        "summary": "Primary MCP customization module. Contains helper utilities, internal tool implementations (with_mcp_context decorated), and register_tools/register_resources/register_prompts glue.",
        "customization_notes": [
            "Add your tool implementations here using the @with_mcp_context pattern.",
            "Register new resources/prompts in register_resources / register_prompts.",
        ],
        "verification_notes": [
            "Exercise via test/test-mcp.py plugin tests.",
        ],
    }),
    (re.compile(r"^src/auth_fastmcp\.py$"), {
        "role": "auth_provider",
        "customization_relevance": "low",
        "summary": "FastMCP auth provider factory (auth0 / keycloak / oidc dispatch).",
        "customization_notes": [
            "Usually untouched. Edit only when switching/adding an auth_type.",
        ],
        "verification_notes": [],
    }),
    (re.compile(r"^src/auth_oidc\.py$"), {
        "role": "auth_oidc",
        "customization_relevance": "none",
        "summary": "Generic OIDC middleware (copied as-is from mcp-base).",
        "customization_notes": [
            "Do not modify. Identical across generated projects.",
        ],
        "verification_notes": [],
    }),
    (re.compile(r"^src/mcp_context\.py$"), {
        "role": "mcp_context",
        "customization_relevance": "none",
        "summary": "MCPContext dataclass and with_mcp_context decorator (copied as-is).",
        "customization_notes": ["Do not modify."],
        "verification_notes": [],
    }),
    (re.compile(r"^src/user_hash\.py$"), {
        "role": "user_hash",
        "customization_relevance": "none",
        "summary": "User ID hashing utilities (copied as-is).",
        "customization_notes": ["Do not modify."],
        "verification_notes": [],
    }),
    (re.compile(r"^src/prompt_registry\.py$"), {
        "role": "prompt_registry",
        "customization_relevance": "low",
        "summary": "Versioned prompt registry with ConfigMap hot-reload.",
        "customization_notes": [
            "Usually reused as-is; add prompts in chart/templates/prompts-configmap.yaml.",
        ],
        "verification_notes": [],
    }),
    (re.compile(r"^Dockerfile$"), {
        "role": "container_prod",
        "customization_relevance": "low",
        "summary": "Production Dockerfile (multi-stage Python build).",
        "customization_notes": [
            "Adjust base image / system deps only if your tools require native libraries.",
        ],
        "verification_notes": ["docker build -t <image> . && docker run --rm <image>"],
    }),
    (re.compile(r"^Dockerfile\.test$"), {
        "role": "container_test",
        "customization_relevance": "low",
        "summary": "Test-mode Dockerfile (no auth) for CI.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^requirements\.txt$"), {
        "role": "python_requirements",
        "customization_relevance": "medium",
        "summary": "Python dependencies for the server.",
        "customization_notes": [
            "Append the packages your tools import (e.g. kubernetes, pydantic models).",
        ],
        "verification_notes": ["pip install -r requirements.txt in a fresh venv."],
    }),
    (re.compile(r"^Makefile$"), {
        "role": "build_makefile",
        "customization_relevance": "low",
        "summary": "Build automation (build, push, test, helm-install targets).",
        "customization_notes": ["Run `python bin/configure-make.py` to generate make.env first."],
        "verification_notes": [],
    }),
    (re.compile(r"^bin/configure-make\.py$"), {
        "role": "config_script",
        "customization_relevance": "low",
        "summary": "Generates make.env (registry, image names, namespace) for the Makefile.",
        "customization_notes": [
            "Run once before `make build`. Re-run when registry/namespace changes.",
        ],
        "verification_notes": [],
    }),
    (re.compile(r"^bin/smoke_test\.py$"), {
        "role": "smoke_test_script",
        "customization_relevance": "low",
        "summary": "Build-time startup smoke test — invokes register_resources/tools/prompts against an in-process FastMCP to catch FastMCP contract violations before deploy.",
        "customization_notes": [
            "Run as `python bin/smoke_test.py` in CI before `make push`/`make helm-install`.",
            "Does not need network, auth credentials, or Kubernetes.",
        ],
        "verification_notes": ["python bin/smoke_test.py — expect exit 0."],
    }),
    (re.compile(r"^chart/Chart\.yaml$"), {
        "role": "helm_chart_metadata",
        "customization_relevance": "low",
        "summary": "Helm chart metadata (name, version, Redis dependency).",
        "customization_notes": [],
        "verification_notes": ["helm lint chart/"],
    }),
    (re.compile(r"^chart/values\.yaml$"), {
        "role": "helm_values",
        "customization_relevance": "medium",
        "summary": "Default Helm values (image, env, ingress, auth).",
        "customization_notes": [
            "Override per-environment via `helm install -f my-values.yaml`.",
        ],
        "verification_notes": ["helm template chart/ -f my-values.yaml"],
    }),
    (re.compile(r"^chart/templates/prompts-configmap\.yaml$"), {
        "role": "helm_prompts_configmap",
        "customization_relevance": "medium",
        "summary": "ConfigMap backing the hot-reload prompt registry.",
        "customization_notes": [
            "Add project-specific prompts here; PromptRegistry will pick them up.",
        ],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/templates/deployment\.yaml$"), {
        "role": "helm_deployment",
        "customization_relevance": "medium",
        "summary": "Kubernetes Deployment — pod spec, container image, env, health probes, resource limits.",
        "customization_notes": [
            "Drive replicas, image, and env via values.yaml; only edit the template for structural changes.",
        ],
        "verification_notes": ["helm template chart/ | kubectl apply --dry-run=client -f -"],
    }),
    (re.compile(r"^chart/templates/service\.yaml$"), {
        "role": "helm_service",
        "customization_relevance": "low",
        "summary": "Kubernetes Service exposing the MCP port (plus optional test-sidecar port).",
        "customization_notes": [
            "Change port numbers and service type via values.yaml (`service.port`, `service.type`).",
        ],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/templates/rolebinding\.yaml$"), {
        "role": "helm_rolebinding",
        "customization_relevance": "medium",
        "summary": "RBAC: secrets-management Role/RoleBinding + bindings to configured operator ClusterRoles.",
        "customization_notes": [
            "Grant additional cluster roles via `operator_cluster_roles` in generate_server_scaffold or values.yaml.",
            "Add project-specific Roles here if the MCP tools need namespaced permissions beyond secrets.",
        ],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/templates/ingress\.yaml$"), {
        "role": "helm_ingress",
        "customization_relevance": "medium",
        "summary": "Ingress for external HTTPS entry; rendered only when `ingress.enabled` is true.",
        "customization_notes": [
            "Configure host, class, and TLS via values.yaml `ingress.*`.",
        ],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/templates/serviceaccount\.yaml$"), {
        "role": "helm_serviceaccount",
        "customization_relevance": "low",
        "summary": "ServiceAccount used by the Deployment; created when `serviceAccount.create` is true.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/templates/configmap\.yaml$"), {
        "role": "helm_oidc_configmap",
        "customization_relevance": "medium",
        "summary": "OIDC configuration ConfigMap (issuer, audience, required_scopes) rendered from values.yaml.",
        "customization_notes": [
            "Adjust auth config via values.yaml `oidc.*`; `required_scopes` drives the scopes advertised on the WWW-Authenticate 401 / PRM endpoint.",
        ],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/templates/hpa\.yaml$"), {
        "role": "helm_hpa",
        "customization_relevance": "low",
        "summary": "HorizontalPodAutoscaler for the Deployment; rendered only when `autoscaling.enabled` is true.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/templates/.+\.yaml$"), {
        "role": "helm_template",
        "customization_relevance": "low",
        "summary": "Helm template (Kubernetes manifest rendered by chart).",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/templates/NOTES\.txt$"), {
        "role": "helm_notes",
        "customization_relevance": "none",
        "summary": "Post-install NOTES shown to operators.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/templates/_helpers\.tpl$"), {
        "role": "helm_helpers",
        "customization_relevance": "none",
        "summary": "Helm template helpers.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^chart/\.helmignore$"), {
        "role": "helm_ignore",
        "customization_relevance": "none",
        "summary": "Patterns excluded from `helm package`.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^test/test-mcp\.py$"), {
        "role": "test_runner",
        "customization_relevance": "low",
        "summary": "Plugin-based test runner entrypoint.",
        "customization_notes": [],
        "verification_notes": ["./test/test-mcp.py --url http://localhost:4201/test --no-auth"],
    }),
    (re.compile(r"^test/get-user-token\.py$"), {
        "role": "test_token_helper",
        "customization_relevance": "none",
        "summary": "Interactive helper to acquire an Auth0 user token.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^test/mcp-auth-proxy\.py$"), {
        "role": "test_auth_proxy",
        "customization_relevance": "none",
        "summary": "Local auth proxy for test sessions.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^test/plugins/__init__\.py$"), {
        "role": "test_plugin_base",
        "customization_relevance": "none",
        "summary": "TestPlugin/TestResult base classes (copied as-is).",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^test/plugins/test_list_resources\.py$"), {
        "role": "test_plugin",
        "customization_relevance": "low",
        "summary": "Standard plugin: verifies resources/list contents.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^test/plugins/test_read_resource\.py$"), {
        "role": "test_plugin",
        "customization_relevance": "low",
        "summary": "Standard plugin: verifies resources/read.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^test/plugins/test_list_prompts\.py$"), {
        "role": "test_plugin",
        "customization_relevance": "low",
        "summary": "Standard plugin: verifies prompts/list.",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^test/plugins/test_example\.py$"), {
        "role": "test_plugin_example",
        "customization_relevance": "high",
        "summary": "Starter test plugin — heavily commented; copy to test/plugins/test_<your_tool>.py for every new @mcp.tool you add.",
        "customization_notes": [
            "REQUIRED for every new tool: copy this file to "
            "test/plugins/test_<your_tool>.py, rename the class to "
            "Test<YourToolPascalCase>, set tool_name to match the @mcp.tool "
            "name, and replace the body with happy-path AND error-path "
            "assertions specific to your tool's contract.",
            "Use ctx.shared to publish IDs (project_id, cluster name, "
            "resource UID) for downstream plugins to reuse.",
        ],
        "verification_notes": [
            "make test              # starts the local no-auth server, runs tests, then stops it",
            "make dev-coverage      # runs locally under coverage.py and reports line/branch coverage",
        ],
    }),
    (re.compile(r"^test/plugins/test_health_endpoints\.py$"), {
        "role": "test_plugin",
        "customization_relevance": "low",
        "summary": "Standard plugin: verifies /healthz and /readyz return 200 with the documented JSON shape (the K8s probe surface).",
        "customization_notes": [],
        "verification_notes": [],
    }),
    (re.compile(r"^test/run-coverage\.py$"), {
        "role": "test_coverage_runner",
        "customization_relevance": "low",
        "summary": "Coverage orchestrator: spawns the test server under `coverage run`, runs the test suite, combines parallel-mode data, prints a report.",
        "customization_notes": [],
        "verification_notes": ["make dev-coverage", "make dev-coverage-html"],
    }),
    (re.compile(r"^test/run-local-tests\.py$"), {
        "role": "test_local_runner",
        "customization_relevance": "low",
        "summary": "Local test orchestrator: starts the no-auth test server, waits for readiness, runs the plugin suite, and tears the server down.",
        "customization_notes": [],
        "verification_notes": ["make test"],
    }),
    (re.compile(r"^test/requirements\.txt$"), {
        "role": "test_requirements",
        "customization_relevance": "low",
        "summary": "Test-only dependencies (coverage, httpx). NOT installed into the production container; install with `pip install -r test/requirements.txt`.",
        "customization_notes": [],
        "verification_notes": ["make dev-deps"],
    }),
    (re.compile(r"^\.coveragerc$"), {
        "role": "coverage_config",
        "customization_relevance": "low",
        "summary": "coverage.py config: source=src, branch coverage on, parallel mode (test server subprocess writes its own data file).",
        "customization_notes": [
            "Add modules to `omit =` if you want to exclude them from the report.",
        ],
        "verification_notes": [],
    }),
]

_DEFAULT_ROLE = {
    "role": "other",
    "customization_relevance": "low",
    "summary": "",
    "customization_notes": [],
    "verification_notes": [],
}


def _unparse(node: Optional[ast.AST]) -> str:
    """Best-effort ast.unparse; returns empty string on failure."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _arg_to_str(arg: ast.arg, default: Optional[ast.AST]) -> str:
    parts = [arg.arg]
    if arg.annotation is not None:
        parts.append(": " + _unparse(arg.annotation))
    if default is not None:
        parts.append(" = " + _unparse(default))
    return "".join(parts)


def _format_signature(node: ast.AST) -> str:
    """Build a signature string like `(a: int, b: str = "x") -> bool`."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    args = node.args
    parts: List[str] = []

    posonly = list(args.posonlyargs or [])
    regular = list(args.args or [])
    defaults = list(args.defaults or [])
    total_pos = len(posonly) + len(regular)
    # defaults apply to the tail of (posonly + regular)
    default_start = total_pos - len(defaults)
    combined = posonly + regular
    for i, a in enumerate(combined):
        d = defaults[i - default_start] if i >= default_start else None
        parts.append(_arg_to_str(a, d))
        if posonly and i == len(posonly) - 1:
            parts.append("/")

    if args.vararg is not None:
        parts.append("*" + _arg_to_str(args.vararg, None))
    elif args.kwonlyargs:
        parts.append("*")

    for a, d in zip(args.kwonlyargs or [], args.kw_defaults or []):
        parts.append(_arg_to_str(a, d))

    if args.kwarg is not None:
        parts.append("**" + _arg_to_str(args.kwarg, None))

    sig = "(" + ", ".join(parts) + ")"
    if node.returns is not None:
        sig += " -> " + _unparse(node.returns)
    return sig


def _docstring_summary(node: ast.AST) -> str:
    """Return the first line of a node's docstring, or ''."""
    try:
        doc = ast.get_docstring(node)
    except Exception:
        doc = None
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def _decorators(node: ast.AST) -> List[str]:
    dec_list = getattr(node, "decorator_list", None) or []
    return [_unparse(d) for d in dec_list if d is not None]


# ----- Docstring section parsing -----------------------------------------
#
# Google-style section parser. Handles:
#   Args:
#       ctx: MCP context with user information
#       name (str): Name to greet
#   Returns:
#       Formatted string response.
#   Raises:
#       ValueError: ...

_SECTION_HEADERS = {
    "args": "args",
    "arguments": "args",
    "parameters": "args",
    "returns": "returns",
    "return": "returns",
    "yields": "returns",
    "yield": "returns",
    "raises": "raises",
    "raise": "raises",
    "exceptions": "raises",
    "except": "raises",
}

_PARAM_RE = re.compile(r"^([A-Za-z_]\w*)\s*(?:\([^)]+\))?\s*:\s*(.*)$")
_RAISES_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*:\s*(.*)$")


def _parse_docstring_sections(docstring: Optional[str]) -> Dict[str, Any]:
    """Parse a Google-style docstring into summary, args, returns, raises."""
    if not docstring:
        return {"summary": "", "parameter_docs": {}, "returns_doc": "", "raises": []}

    lines = docstring.strip().splitlines()
    summary_lines: List[str] = []
    rest_start = len(lines)
    for i, line in enumerate(lines):
        if not line.strip():
            rest_start = i + 1
            break
        summary_lines.append(line.strip())
    summary = " ".join(summary_lines).strip()

    parameter_docs: Dict[str, str] = {}
    returns_doc_parts: List[str] = []
    raises: List[str] = []

    current_section: Optional[str] = None
    current_param: Optional[str] = None
    current_buf: List[str] = []

    def flush_param() -> None:
        nonlocal current_param, current_buf
        if current_param is not None:
            text = " ".join(p.strip() for p in current_buf if p.strip()).strip()
            if text:
                parameter_docs[current_param] = text
        current_param = None
        current_buf = []

    for line in lines[rest_start:]:
        stripped = line.strip()
        low = stripped.lower().rstrip(":")
        if low in _SECTION_HEADERS and stripped.endswith(":"):
            flush_param()
            current_section = _SECTION_HEADERS[low]
            continue

        if current_section == "args":
            m = _PARAM_RE.match(stripped)
            if m:
                flush_param()
                current_param = m.group(1)
                current_buf = [m.group(2)]
            elif current_param is not None and stripped:
                current_buf.append(stripped)
        elif current_section == "returns":
            if stripped:
                returns_doc_parts.append(stripped)
        elif current_section == "raises":
            m = _RAISES_RE.match(stripped)
            if m:
                name = m.group(1)
                if name and name not in raises:
                    raises.append(name)

    flush_param()

    return {
        "summary": summary,
        "parameter_docs": parameter_docs,
        "returns_doc": " ".join(returns_doc_parts).strip(),
        "raises": raises,
    }


# ----- Exposure + usage-role classification ------------------------------

_REGISTER_NAMES = {
    "register_tools": "tool_registration",
    "register_resources": "resource_registration",
    "register_prompts": "prompt_registration",
}

_MCP_DECORATOR_RE = re.compile(r"^mcp\.(tool|resource|prompt)\b")


def _detect_exposed_as(decorators: List[str]) -> Optional[Dict[str, str]]:
    """Detect @mcp.tool / @mcp.resource / @mcp.prompt decorators."""
    for raw in decorators:
        d = raw.strip()
        m = _MCP_DECORATOR_RE.match(d)
        if not m:
            continue
        kind = m.group(1)
        paren_open = d.find("(")
        inner = d[paren_open + 1 : d.rfind(")")] if paren_open != -1 else ""
        name_m = re.search(r"""name\s*=\s*['"]([^'"]+)['"]""", inner)
        if kind == "tool":
            return {"kind": "tool", "name": name_m.group(1) if name_m else ""}
        if kind == "prompt":
            return {"kind": "prompt", "name": name_m.group(1) if name_m else ""}
        if kind == "resource":
            uri_m = re.search(r"""['"]([^'"]+)['"]""", inner)
            return {"kind": "resource", "uri": uri_m.group(1) if uri_m else ""}
    return None


def _classify_usage_role(
    name: str,
    decorators: List[str],
    exposed_as: Optional[Dict[str, str]],
    is_class: bool,
    file_role: str,
) -> str:
    """Assign a usage_role tag to a symbol."""
    if exposed_as is not None:
        return {
            "tool": "tool_registration",
            "resource": "resource_registration",
            "prompt": "prompt_registration",
        }[exposed_as["kind"]]

    low = [d.lower() for d in decorators]
    if any("with_mcp_context" in d for d in low):
        return "admin_operation" if name.startswith("admin_") else "tool_implementation"

    if name in _REGISTER_NAMES:
        return _REGISTER_NAMES[name]

    if name.endswith("_impl"):
        return "admin_operation" if name.startswith("admin_") else "tool_implementation"

    if file_role in _FRAMEWORK_FILE_ROLES:
        return "context_adapter"

    return "helper"


def _derive_depends_on(
    decorators: List[str],
    signature: str,
    imports_seen: List[str],
) -> List[str]:
    deps: List[str] = []
    for d in decorators:
        if "with_mcp_context" in d:
            deps.append("with_mcp_context")
    if "MCPContext" in signature:
        deps.append("MCPContext")
    if "fastmcp.Context" in signature or re.search(r"\bContext\b", signature) and not deps:
        # FastMCP request Context parameter
        if "ctx: Context" in signature or "ctx=Context" in signature or "Context = None" in signature:
            deps.append("fastmcp.Context")
    for mod in ("prompt_registry", "auth_fastmcp", "auth_oidc"):
        if mod in imports_seen and mod not in deps:
            # Only tag if caller actually references the module in this symbol.
            # Module-level imports already indicate potential dependency;
            # per-symbol precision requires body inspection (kept light).
            pass
    seen: Dict[str, None] = {}
    for d in deps:
        if d not in seen:
            seen[d] = None
    return list(seen.keys())


def _derive_required_context(deps: List[str], signature: str) -> List[str]:
    ctx: List[str] = []
    if "with_mcp_context" in deps or "MCPContext" in deps:
        ctx.append("authenticated MCP request context (user claims from JWT)")
    elif "fastmcp.Context" in deps or "Context = None" in signature:
        ctx.append("FastMCP request Context")
    return ctx


def _intended_usage(usage_role: str) -> str:
    return {
        "tool_implementation": (
            "Internal implementation invoked through MCP tool registration. "
            "Do not import directly; invoke through the registered tool."
        ),
        "tool_registration": (
            "Import and call once from the server entrypoint at startup to "
            "register tools on the FastMCP instance. Modify to expose new tools."
        ),
        "resource_registration": (
            "Import and call once from the server entrypoint at startup to "
            "register MCP resources. Modify to add project-specific resources."
        ),
        "prompt_registration": (
            "Import and call once from the server entrypoint at startup to "
            "register MCP prompts from the prompt registry."
        ),
        "helper": (
            "Module-level utility. Import and call directly from other code "
            "in this module or from new tool implementations."
        ),
        "context_adapter": (
            "Framework adapter copied as-is from mcp-base. Do not modify or "
            "re-implement; treat as opaque infrastructure."
        ),
        "admin_operation": (
            "Internal admin implementation invoked through MCP tool registration. "
            "Do not import directly; invoke through the registered admin tool."
        ),
    }.get(usage_role, "Standard Python symbol; consult docstring before use.")


_FRAMEWORK_FILE_ROLES = {
    "mcp_context",
    "auth_provider",
    "auth_oidc",
    "user_hash",
    "prompt_registry",
}


def _derive_api_status(
    is_placeholder: bool,
    file_role: str,
    usage_role: str,
) -> str:
    """Export intended visibility. Values:
      - scaffold_placeholder: example/seed code meant to be replaced
      - framework_internal:   copied-from-mcp-base infra, treat as opaque
      - internal:             implementation detail of this module
      - module_public:        callable directly, but scoped to this module's
                              own code (helpers / local utilities) — not a
                              cross-module external API
      - public:               meant to be imported or wired up by user code
                              from outside this module (registration glue)
    """
    if is_placeholder:
        return "scaffold_placeholder"
    if file_role in _FRAMEWORK_FILE_ROLES:
        return "framework_internal"
    if usage_role in ("tool_implementation", "admin_operation"):
        return "internal"
    if usage_role == "helper":
        return "module_public"
    return "public"


def _derive_opacity(api_status: str) -> str:
    """Express whether the symbol should be treated as opaque.
      - opaque:                     ignore unless replacing/removing
      - inspect_if_modifying_module: read only when editing this module
      - intended_for_direct_use:    import/call freely
    """
    if api_status in ("scaffold_placeholder", "framework_internal"):
        return "opaque"
    if api_status == "internal":
        return "inspect_if_modifying_module"
    return "intended_for_direct_use"


_PLACEHOLDER_NAME_PREFIXES = ("example_", "TestExample")
_PLACEHOLDER_FILE_ROLES = {"test_plugin_example"}


def _is_placeholder_symbol(name: str, file_role: str) -> bool:
    """True when the symbol is a scaffold seed meant to be replaced/copied,
    not extended in place. Derived from naming convention + file role.
    """
    if file_role in _PLACEHOLDER_FILE_ROLES:
        return True
    return any(name.startswith(prefix) for prefix in _PLACEHOLDER_NAME_PREFIXES)


def _detect_delegates_to(func_node: ast.AST) -> Optional[str]:
    """If the function awaits an `<name>_impl(...)` call, return that name.

    Captures the standard scaffold pattern where a decorated @mcp.tool
    handler is a thin wrapper that forwards to a top-level <name>_impl
    function. Lets us emit an explicit runtime-name ↔ implementation link
    without the agent reading the file.
    """
    for n in ast.walk(func_node):
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call):
            callee = _unparse(n.value.func)
            if callee.endswith("_impl") and "." not in callee:
                return callee
    return None


def _detect_side_effects(func_node: ast.AST) -> List[str]:
    """Body-walk for common side-effect patterns."""
    effects: set = set()
    for n in ast.walk(func_node):
        if isinstance(n, ast.Call):
            fn_src = _unparse(n.func)
            if not fn_src:
                continue
            if fn_src.endswith(".info") or fn_src.endswith(".warning") or fn_src.endswith(".error"):
                if fn_src.startswith("logger.") or "ctx" in fn_src:
                    effects.add("writes log/context messages")
            if "reload_prompt_registry" in fn_src:
                effects.add("reloads prompt registry from ConfigMap")
            if fn_src.startswith("asyncio.to_thread"):
                effects.add("runs blocking I/O on a worker thread")
            if fn_src.startswith("os.getenv") or fn_src.startswith("os.environ"):
                effects.add("reads environment variables")
            if fn_src.startswith("open(") or fn_src == "open":
                effects.add("reads/writes local files")
            if fn_src.startswith("httpx.") or fn_src.startswith("requests."):
                effects.add("performs outbound HTTP requests")
        elif isinstance(n, ast.Raise):
            effects.add("raises exceptions on error paths")
        elif isinstance(n, ast.Attribute):
            src = _unparse(n)
            if src.startswith("os.environ"):
                effects.add("reads environment variables")
    return sorted(effects)


def _is_public(name: str) -> bool:
    return bool(name) and not name.startswith("_")


def _enrich_parameter_docs(
    parameter_docs: Dict[str, str],
    signature: str,
    decorators: List[str],
) -> Dict[str, str]:
    """Fill obvious ctx parameter docs from signature/decorator context.

    Only fills when the signal is unambiguous — when the agent could
    read it off the signature anyway. Leaves non-obvious parameters
    (domain-specific names like `cluster_name`, `namespace`) untouched.
    """
    if "ctx" in parameter_docs and parameter_docs["ctx"]:
        return parameter_docs
    if "ctx" not in signature:
        return parameter_docs
    has_with_mcp_context = any("with_mcp_context" in d for d in decorators)
    if has_with_mcp_context or "MCPContext" in signature:
        parameter_docs["ctx"] = (
            "Authenticated MCP request context with user claims extracted "
            "from the verified JWT (sub, preferred_username, email, ...)."
        )
    elif "Context = None" in signature or "ctx: Context" in signature:
        parameter_docs["ctx"] = (
            "FastMCP request Context injected by the runtime; used for "
            "logging and progress notifications back to the MCP client."
        )
    return parameter_docs


def _infer_returns_doc(
    existing: str,
    signature: str,
    usage_role: str,
) -> str:
    """Synthesize returns_doc only for rigid MCP-exposed patterns where the
    return shape is fixed by the protocol. Otherwise leave blank.
    """
    if existing:
        return existing
    if "-> str" not in signature:
        return ""
    if usage_role in ("tool_implementation", "admin_operation"):
        return "Formatted string response returned to the MCP tool caller."
    return ""


def _function_record(
    node: ast.AST,
    *,
    kind_override: Optional[str] = None,
    file_role: str = "other",
    imports_seen: Optional[List[str]] = None,
    is_class_member: bool = False,
) -> Dict[str, Any]:
    """Build an enriched symbol record for a function/method node."""
    is_async = isinstance(node, ast.AsyncFunctionDef)
    default_kind = "async_function" if is_async else "function"
    if is_class_member:
        default_kind = "async_method" if is_async else "method"
    kind = kind_override or default_kind

    decorators = _decorators(node)
    signature = _format_signature(node)
    exposed_as = _detect_exposed_as(decorators)
    doc = _parse_docstring_sections(ast.get_docstring(node))
    usage_role = _classify_usage_role(
        name=node.name,
        decorators=decorators,
        exposed_as=exposed_as,
        is_class=False,
        file_role=file_role,
    )
    depends_on = _derive_depends_on(decorators, signature, imports_seen or [])
    required_context = _derive_required_context(depends_on, signature)
    side_effects = _detect_side_effects(node)
    intended_usage = _intended_usage(usage_role)
    is_placeholder = _is_placeholder_symbol(node.name, file_role)
    api_status = _derive_api_status(is_placeholder, file_role, usage_role)
    opacity = _derive_opacity(api_status)
    parameter_docs = _enrich_parameter_docs(dict(doc["parameter_docs"]), signature, decorators)
    returns_doc = _infer_returns_doc(doc["returns_doc"], signature, usage_role)

    rec: Dict[str, Any] = {
        "name": node.name,
        "kind": kind,
        "line_hint": node.lineno,
        "signature": signature,
        "decorators": decorators,
        "summary": doc["summary"] or _docstring_summary(node),
        "parameter_docs": parameter_docs,
        "returns_doc": returns_doc,
        "raises": doc["raises"],
        "side_effects": side_effects,
        "usage_role": usage_role,
        "api_status": api_status,
        "opacity": opacity,
        "depends_on": depends_on,
        "required_context": required_context,
        "intended_usage": intended_usage,
        "is_placeholder": is_placeholder,
    }
    if exposed_as is not None:
        rec["exposed_as"] = exposed_as
    return rec


def _class_record(
    node: ast.ClassDef,
    *,
    file_role: str = "other",
    imports_seen: Optional[List[str]] = None,
) -> Dict[str, Any]:
    methods: List[Dict[str, Any]] = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Public methods + __init__ (the constructor contract).
            if _is_public(item.name) or item.name == "__init__":
                methods.append(_function_record(
                    item,
                    file_role=file_role,
                    imports_seen=imports_seen,
                    is_class_member=True,
                ))

    decorators = _decorators(node)
    doc_sections = _parse_docstring_sections(ast.get_docstring(node))
    usage_role = _classify_usage_role(
        name=node.name,
        decorators=decorators,
        exposed_as=None,
        is_class=True,
        file_role=file_role,
    )

    is_placeholder = _is_placeholder_symbol(node.name, file_role)
    api_status = _derive_api_status(is_placeholder, file_role, usage_role)
    opacity = _derive_opacity(api_status)

    return {
        "name": node.name,
        "kind": "class",
        "line_hint": node.lineno,
        "decorators": decorators,
        "base_classes": [_unparse(b) for b in (node.bases or []) if b is not None],
        "summary": doc_sections["summary"] or _docstring_summary(node),
        "parameter_docs": doc_sections["parameter_docs"],
        "raises": doc_sections["raises"],
        "usage_role": usage_role,
        "api_status": api_status,
        "opacity": opacity,
        "intended_usage": _intended_usage(usage_role),
        "is_placeholder": is_placeholder,
        "methods": methods,
    }


def _walk_registered_surface(
    register_node: ast.AST,
    *,
    file_role: str,
    imports_seen: List[str],
) -> List[Dict[str, Any]]:
    """Find @mcp.tool / @mcp.resource / @mcp.prompt decorated functions
    nested inside a register_* function and surface them as top-level
    registered_surface entries.
    """
    registered: List[Dict[str, Any]] = []
    parent_name = getattr(register_node, "name", "")
    for node in ast.walk(register_node):
        if node is register_node:
            continue
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decs = _decorators(node)
        exposed = _detect_exposed_as(decs)
        if exposed is None:
            continue
        rec = _function_record(
            node,
            file_role=file_role,
            imports_seen=imports_seen,
        )
        rec["parent"] = parent_name
        delegate = _detect_delegates_to(node)
        if delegate:
            rec["delegates_to"] = delegate
        registered.append(rec)
    return registered


_KNOWN_RUNTIME_DEPS = {
    "fastmcp": "FastMCP framework",
    "mcp_context": "MCPContext / with_mcp_context",
    "prompt_registry": "PromptRegistry (ConfigMap-backed, hot-reload)",
    "auth_fastmcp": "FastMCP auth provider factory",
    "auth_oidc": "Generic OIDC middleware",
    "user_hash": "User ID hashing utilities",
    "artifact_store": "Scaffold artifact store (mcp-base internal)",
    "redis": "Redis session store",
    "kubernetes": "Kubernetes API client",
    "httpx": "HTTP client (outbound)",
    "jinja2": "Jinja2 templating",
    "pydantic": "Pydantic validation",
    "yaml": "YAML parsing",
}


def _derive_module_flags(
    symbols: List[Dict[str, Any]],
    registered_surface: List[Dict[str, Any]],
    role_meta: Dict[str, Any],
    imports: List[str],
) -> Dict[str, Any]:
    has_registration = any(
        s.get("usage_role", "").endswith("_registration") for s in symbols
    )
    has_impl = any(
        s.get("usage_role") in ("tool_implementation", "admin_operation")
        for s in symbols
    ) or bool(registered_surface)
    has_helpers = any(s.get("usage_role") == "helper" for s in symbols)

    runtime_deps = [
        _KNOWN_RUNTIME_DEPS[imp] for imp in imports if imp in _KNOWN_RUNTIME_DEPS
    ]

    return {
        "contains_business_logic": has_impl,
        "contains_registration": has_registration,
        "contains_helpers": has_helpers,
        "primary_customization_surface": role_meta.get("customization_relevance") == "high",
        "runtime_dependencies": runtime_deps,
    }


def _extract_python_api(
    content: str,
    *,
    file_role: str = "other",
    max_symbols: int = 40,
    max_imports: int = 40,
) -> Dict[str, Any]:
    """
    AST-extract the API surface of a Python source file.

    Returns a dict with:
      - symbols: top-level public function/class records with full contract
                 metadata (signature, decorators, parameter_docs, returns_doc,
                 raises, side_effects, usage_role, depends_on, required_context,
                 intended_usage, exposed_as, methods for classes)
      - exports: public top-level symbol names
      - imports: deduplicated top-level module imports
      - registered_surface: @mcp.tool / @mcp.resource / @mcp.prompt handlers
                 nested inside register_* functions (MCP runtime surface)

    On SyntaxError, returns an empty structure rather than raising — the
    scaffold's stored bytes remain authoritative even if extraction fails.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {
            "symbols": [],
            "exports": [],
            "imports": [],
            "registered_surface": [],
        }

    # Pass 1: collect imports so per-symbol records can reason about deps.
    seen_imports: Dict[str, None] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top not in seen_imports and len(seen_imports) < max_imports:
                    seen_imports[top] = None
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                top = node.module.split(".", 1)[0]
                if top not in seen_imports and len(seen_imports) < max_imports:
                    seen_imports[top] = None
    imports_list = list(seen_imports.keys())

    # Pass 2: top-level public symbols + nested MCP surface.
    symbols: List[Dict[str, Any]] = []
    exports: List[str] = []
    registered_surface: List[Dict[str, Any]] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not _is_public(node.name):
                continue
            if len(symbols) < max_symbols:
                symbols.append(_function_record(
                    node,
                    file_role=file_role,
                    imports_seen=imports_list,
                ))
                exports.append(node.name)
            if isinstance(node, ast.FunctionDef) and node.name in _REGISTER_NAMES:
                registered_surface.extend(_walk_registered_surface(
                    node,
                    file_role=file_role,
                    imports_seen=imports_list,
                ))
        elif isinstance(node, ast.ClassDef):
            if not _is_public(node.name):
                continue
            if len(symbols) < max_symbols:
                symbols.append(_class_record(
                    node,
                    file_role=file_role,
                    imports_seen=imports_list,
                ))
                exports.append(node.name)

    # Back-link impls to their MCP exposure. The registered handler
    # delegates_to a top-level _impl; mirror that as exposed_via on the
    # impl so the agent can start from either end of the call graph.
    impl_index = {s["name"]: s for s in symbols}
    for reg in registered_surface:
        target = reg.get("delegates_to")
        if not target or target not in impl_index:
            continue
        impl = impl_index[target]
        exposed_as = reg.get("exposed_as") or {}
        impl["exposed_via"] = {
            "handler": reg["name"],
            "kind": exposed_as.get("kind", ""),
            **({"name": exposed_as["name"]} if "name" in exposed_as else {}),
            **({"uri": exposed_as["uri"]} if "uri" in exposed_as else {}),
        }

    return {
        "symbols": symbols,
        "exports": exports,
        "imports": imports_list,
        "registered_surface": registered_surface,
    }


# ----- Operational metadata helpers --------------------------------------

_EXECUTABLE_PATH_RULES = [
    re.compile(r"^bin/.+\.py$"),
    re.compile(r"^test/[^/]+\.py$"),  # test/test-mcp.py, test/get-user-token.py, etc.
]


def _is_executable_path(path: str) -> bool:
    """True if the generated file should be marked +x after write."""
    return any(rule.match(path) for rule in _EXECUTABLE_PATH_RULES)


def _detect_line_endings(content: str) -> str:
    """Return 'crlf' if the content contains any \\r\\n, else 'lf'."""
    return "crlf" if "\r\n" in content else "lf"


def _infer_role(path: str) -> Dict[str, Any]:
    """Look up the role/relevance/summary metadata for a generated path."""
    for pattern, meta in _ROLE_RULES:
        if pattern.match(path):
            return dict(meta)
    return dict(_DEFAULT_ROLE)


def build_artifact_metadata(
    project_id: str,
    path: str,
    *,
    include_symbols: bool = True,
    include_imports: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Build a compact metadata record for a stored artifact.

    Returns None when the artifact does not exist. The returned dict is
    deliberately lightweight — no file contents — so metadata tools can be
    invoked without bloating model context. It is, however, rich enough
    to serve as a materialization contract: the agent can write the file
    from resources/read bytes, chmod it, and import from it without ever
    pulling the file into model context.

    Operational fields (always present):
      - content_encoding, line_endings, hash_algorithm
      - executable, permissions, post_write_actions
    """
    artifact = artifact_store.get(project_id, path)
    if artifact is None:
        return None

    role_meta = _infer_role(path)
    is_executable = _is_executable_path(path)
    post_write_actions = [f"chmod +x {path}"] if is_executable else []

    record: Dict[str, Any] = {
        "project_id": project_id,
        "path": path,
        "uri": f"scaffold://{project_id}/{path}",
        "mime_type": artifact.mime_type,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
        "hash_algorithm": "sha256",
        "content_encoding": "utf-8",
        "line_endings": _detect_line_endings(artifact.content),
        "executable": is_executable,
        "permissions": "0755" if is_executable else "0644",
        "post_write_actions": post_write_actions,
        **role_meta,
    }

    if artifact.mime_type == "text/x-python":
        api = _extract_python_api(artifact.content, file_role=role_meta.get("role", "other"))
        module_flags = _derive_module_flags(
            symbols=api["symbols"],
            registered_surface=api["registered_surface"],
            role_meta=role_meta,
            imports=api["imports"],
        )
        if include_symbols:
            record["symbols"] = api["symbols"]
            record["exports"] = api["exports"]
            record["registered_surface"] = api["registered_surface"]
        if include_imports:
            record["imports"] = api["imports"]
        record.update(module_flags)

    return record


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
    result += "- `container/Dockerfile.test.j2` - Test container build (no auth, lands at `test/Dockerfile`, FROM main image)\n"
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
    port: int = 4200,
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
        port: HTTP server port (default: 4200; test sidecar uses port+1=4201)
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
    port: int = 4200,
    default_namespace: str = "default",
    operator_cluster_roles: Optional[str] = None,
    include_helm: bool = True,
    include_test: bool = True,
    auth_type: Literal["auth0", "keycloak", "oidc"] = "auth0"
) -> Dict[str, Any]:
    """
    Generate complete MCP server project scaffold (resource-first).

    Returns a COMPACT manifest — no file bytes in the tool output. Every
    generated file is stored and exposed as a concrete MCP resource at
    `scaffold://{project_id}/{path}`. Bulk byte transfer is intended to
    happen via `resources/read`; tool outputs stay context-light.

    ========================================================================
    RETRIEVAL CONTRACT (resource-first)
    ========================================================================

    Primary (bulk bytes):
        resources/read("scaffold://{project_id}/{path}")
        → returns exact file bytes. Verify each file's local hash matches
          the artifact's `sha256`.

    Primary (coordination metadata):
        list_scaffold_artifact_metadata(project_id)
        read_scaffold_artifact_metadata(project_id, path)
        → compact metadata (role, relevance, symbols, notes). No contents.

    Last-resort compatibility fallback (context-bloat risk):
        read_scaffold_artifact(project_id, path)
        → returns full file bytes in tool output. DO NOT USE if
          resources/read is available. Reserved for tool-only proxy
          aggregators that drop resources entirely (e.g. OpenAI's
          codex_apps).

    ========================================================================
    HARD GATE
    ========================================================================

    Scaffold validity requires every on-disk file to be byte-identical to
    the stored artifact. Verify via `sha256` after writing. On ANY retrieval
    failure, STOP and produce SCAFFOLD_RETRIEVAL_FAILURE.md
    (template in the `failure_report_template` field). Do NOT:
      - Reconstruct from memory
      - Render templates as a substitute (`render_template` is NOT a fallback)
      - Create placeholder files
      - Infer missing contents from filenames
      - Continue to customization with an incomplete scaffold

    SCAFFOLD_INVENTORY.md may be produced only after 100% verified retrieval.

    ========================================================================
    INTENDED AGENT WORKFLOW
    ========================================================================

    1. Call generate_server_scaffold. Read the `artifacts` manifest — each
       entry has path, uri, mime_type, size_bytes, sha256, role,
       customization_relevance, and summary.
    2. For each artifact, resources/read the uri and write bytes to the
       local workspace at `path`.
    3. Verify local SHA256 matches `artifacts[i].sha256`.
    4. Create SCAFFOLD_INVENTORY.md only after 100% hash match.
    5. Inspect only files where `customization_relevance` is high or medium.
       Use read_scaffold_artifact_metadata for symbols/notes before opening
       files locally.
    6. Customize locally; chmod +x bin/*; configure-make.py; build/push/deploy.

    ========================================================================

    The scaffold includes:
    - src/ - Server code, tools, auth modules, test server
    - bin/ - Configuration scripts (bin/configure-make.py)
    - chart/ - Complete Helm chart with ALL templates
    - test/ - Plugin-based test framework
    - Dockerfile, test/Dockerfile, Makefile, requirements.txt

    NOTE: Utility scripts (setup-oidc, add-user, etc.) are available via
    the mcp-base CLI (`pip install mcp-base`). Exception:
    bin/configure-make.py IS included to generate make.env.

    CRITICAL USAGE RULES:
    1. NON-DEVIATION: scaffold artifacts are the ONLY source of project files.
    2. ERROR HANDLING: on retrieval error, report the exact error and retry;
       do NOT substitute alternate scaffolds or rendered templates.
    3. PARAMETER DEFAULTS: don't override include_helm / include_test unless
       explicitly requested.

    Args:
        server_name: Human-readable server name (e.g., "Kubernetes Manager MCP")
        output_description: Deprecated - included for backward compatibility only (ignored)
        port: HTTP server port (default: 4200; test sidecar uses port+1=4201)
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
        Compact JSON manifest — no file contents. Shape:
        {
            "project_id": "server-name-abc123",
            "server_name": "Server Name",
            "file_count": 37,
            "artifacts": [
                {
                    "path": "src/foo_server.py",
                    "uri": "scaffold://server-name-abc123/src/foo_server.py",
                    "mime_type": "text/x-python",
                    "size_bytes": 4096,
                    "sha256": "<hex digest>",
                    "role": "server_entrypoint",
                    "customization_relevance": "medium",
                    "summary": "..."
                },
                ...
            ],
            "retrieval_contract": { ... },
            "workflow": [ ... ],
            "failure_report_template": { ... },
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
        "module_name": server_name_snake,  # used by helm/templates/deployment.yaml.j2
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
        ("container/Dockerfile.test.j2", "test/Dockerfile"),
    ]

    container_static = [
        ("container/requirements.txt", "requirements.txt"),
    ]

    # Makefile
    makefile = [
        ("Makefile.j2", "Makefile"),
    ]

    # Project-level config (canonical source for build + deployment defaults)
    # plus the release values overlay (deployment artifact at repo root).
    project_config_templates = [
        ("mcp-project.yaml.j2", "mcp-project.yaml"),
        # The release values file is named after the helm release. The
        # Makefile's HELM_VALUES_FILE default ($(HELM_RELEASE).yaml) picks
        # it up automatically.
        ("release-values.yaml.j2", f"{chart_name}.yaml"),
    ]

    # Bin scripts (coordinate with Dockerfile/Makefile/mcp-project.yaml)
    bin_templates = [
        # sync-config is the canonical source-of-truth synchronizer:
        # reads mcp-project.yaml, writes make.env.
        ("bin/sync-config.py.j2", "bin/sync-config.py"),
        # configure-make.py is now a compat wrapper that delegates to
        # sync-config.py — kept so old docs/CI still work.
        ("bin/configure-make.py.j2", "bin/configure-make.py"),
        ("bin/smoke_test.py.j2", "bin/smoke_test.py"),
    ]

    # Process template files
    for template_path, output_path in (
        server_templates
        + container_templates
        + makefile
        + project_config_templates
        + bin_templates
    ):
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
            # Coverage harness — runs the no-auth test server under
            # `coverage run` and combines parallel-mode data files.
            ("test/run-coverage.py.j2", "test/run-coverage.py"),
            ("test/run-local-tests.py.j2", "test/run-local-tests.py"),
            (".coveragerc.j2", ".coveragerc"),
        ]

        test_static = [
            ("test/plugin_base.py", "test/plugins/__init__.py"),
            ("test/requirements.txt", "test/requirements.txt"),
            ("test/get_user_token.py", "test/get-user-token.py"),
            ("test/auth_proxy.py", "test/mcp-auth-proxy.py"),
            ("test/test_list_resources.py", "test/plugins/test_list_resources.py"),
            ("test/test_read_resource.py", "test/plugins/test_read_resource.py"),
            ("test/test_list_prompts.py", "test/plugins/test_list_prompts.py"),
            # Always-available smoke test against the K8s probe surface.
            ("test/test_health_endpoints.py", "test/plugins/test_health_endpoints.py"),
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

        # Example test plugin (richly-commented starter — agents copy this
        # to test/plugins/test_<your_tool>.py when adding a new @mcp.tool
        # to src/<server>_tools.py). Generated from
        # templates/test/test_example_custom_tool.py.j2 so the example
        # stays in sync with the rest of the test harness.
        try:
            example_plugin_template = jinja_env.get_template(
                "test/test_example_custom_tool.py.j2"
            )
            files["test/plugins/test_example.py"] = example_plugin_template.render(
                **variables
            )
        except Exception as e:
            files["test/plugins/test_example.py"] = f"# Error rendering: {e}"

    # NOTE: Utility scripts (add-user, setup-oidc, setup-rbac, etc.) are NOT included in the
    # scaffold. They are available via the mcp-base CLI (pip install mcp-base) to avoid context
    # bloat - these large utility scripts don't need customization and can be run via mcp-base.

    # Generate unique project ID for artifact storage
    project_id = f"{server_name_kebab}-{uuid.uuid4().hex[:8]}"

    # Store all files as artifacts (size_bytes/sha256 computed in Artifact.__post_init__)
    for path, content in files.items():
        mime_type = get_mime_type_for_path(path)
        artifact_store.store(
            project_id=project_id,
            path=path,
            content=content,
            mime_type=mime_type,
            description=f"Generated file for {server_name}"
        )

    # Build the compact artifacts manifest. Each entry carries URI + digest
    # + operational fields (permissions, post-write actions, line endings)
    # + role hints + module-level flags (contains_business_logic, etc.)
    # so the agent can plan assembly and customization without reading any
    # file bytes into model context. Python symbol/import surfaces are NOT
    # included at this level — call list_scaffold_artifact_metadata or
    # read_scaffold_artifact_metadata for API-contract details when
    # customization is imminent.
    _MODULE_FLAG_KEYS = (
        "contains_business_logic",
        "contains_registration",
        "contains_helpers",
        "primary_customization_surface",
        "runtime_dependencies",
    )
    artifacts_manifest: List[Dict[str, Any]] = []
    for path in sorted(files.keys()):
        meta = build_artifact_metadata(
            project_id, path,
            include_symbols=False,
            include_imports=False,
        )
        if meta is None:
            continue
        entry = {
            "path": meta["path"],
            "uri": meta["uri"],
            "mime_type": meta["mime_type"],
            "size_bytes": meta["size_bytes"],
            "sha256": meta["sha256"],
            "hash_algorithm": meta["hash_algorithm"],
            "content_encoding": meta["content_encoding"],
            "line_endings": meta["line_endings"],
            "executable": meta["executable"],
            "permissions": meta["permissions"],
            "post_write_actions": meta["post_write_actions"],
            "role": meta["role"],
            "customization_relevance": meta["customization_relevance"],
            "summary": meta["summary"],
        }
        for key in _MODULE_FLAG_KEYS:
            if key in meta:
                entry[key] = meta[key]
        artifacts_manifest.append(entry)

    result = {
        "project_id": project_id,
        "server_name": server_name,
        "server_name_snake": server_name_snake,
        "server_name_kebab": server_name_kebab,
        "file_count": len(files),
        "artifacts": artifacts_manifest,
        "retrieval_contract": {
            "bulk_bytes": (
                "Use resources/read for scaffold://{project_id}/{path} URIs. "
                "Every artifact is registered as a concrete MCP resource."
            ),
            "metadata": (
                "Use list_scaffold_artifact_metadata(project_id) or "
                "read_scaffold_artifact_metadata(project_id, path) for coordination "
                "data (role, relevance, symbols, notes) without file contents."
            ),
            "fallback_full_content": (
                "read_scaffold_artifact(project_id, path) is a LAST-RESORT "
                "fallback for tool-only proxy aggregators (e.g. OpenAI's "
                "codex_apps) that drop resources. DO NOT USE if resources/read "
                "is available — it returns full bytes into tool output and "
                "will blow model context for any non-trivial scaffold."
            ),
            "gate": (
                "Scaffold validity requires each on-disk file to be byte-identical "
                "to the stored artifact (verify via sha256). On any retrieval "
                "failure, produce SCAFFOLD_RETRIEVAL_FAILURE.md and stop — do not "
                "render templates, reconstruct, or substitute."
            ),
        },
        "workflow": [
            "1. For each artifact URI, call resources/read and write exact bytes to ./<path>.",
            "2. Verify local hash == artifacts[i].sha256 for every file.",
            "3. Only after 100% verification, create SCAFFOLD_INVENTORY.md.",
            "4. Inspect only files with customization_relevance='high' or 'medium'; "
            "use read_scaffold_artifact_metadata for symbols/notes before opening locally.",
            "5. Customize locally. chmod +x bin/*.",
            f"6. python bin/configure-make.py && make build && make push && make helm-install.",
        ],
        "failure_report_template": {
            "filename": "SCAFFOLD_RETRIEVAL_FAILURE.md",
            "markdown": (
                "# Scaffold Retrieval Failure\n\n"
                f"- Project ID: {project_id}\n"
                f"- Expected files: {len(files)}\n"
                "- Retrieved files: <count>\n"
                "- Failed files: <count>\n"
                "- Files written to disk: none\n\n"
                "## Failed Artifact Reads\n\n"
                "| Path | URI | Error |\n"
                "| --- | --- | --- |\n"
                "| <path> | <scaffold uri> | <exact error message> |\n\n"
                "## Conclusion\n\n"
                "Scaffold generation returned a manifest, but scaffold artifacts were\n"
                "not retrievable via resources/read (scaffold://...) nor via\n"
                "read_scaffold_artifact. No scaffold files were written because\n"
                "doing so would violate the exact-artifact invariant.\n\n"
                "## Suggested Next Step\n\n"
                "Verify that the MCP server exposes scaffold:// resources or\n"
                "read_scaffold_artifact in the same session, and that the project_id\n"
                "has not expired. Retry generation if the server was restarted.\n"
            ),
        },
        "warnings": [],
        "truncated": False,
    }

    if output_description == "summary":
        result["summary"] = (
            f"Generated {len(files)} files for {server_name}. "
            f"Primary retrieval: resources/read('scaffold://{project_id}/<path>'). "
            f"Use list_scaffold_artifact_metadata / read_scaffold_artifact_metadata for "
            f"coordination data without file contents. read_scaffold_artifact is a "
            f"compatibility fallback only. On any retrieval failure, stop and produce "
            f"SCAFFOLD_RETRIEVAL_FAILURE.md."
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
        port: int = 4200,
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
        port: int = 4200,
        default_namespace: str = "default",
        operator_cluster_roles: Optional[str] = None,
        include_helm: bool = True,
        include_test: bool = True,
        auth_type: Literal["auth0", "keycloak", "oidc"] = "auth0"
    ) -> Dict[str, Any]:
        """
        Generate an MCP server project scaffold (resource-first).

        Returns a COMPACT manifest: per-artifact metadata (path, uri,
        mime_type, size_bytes, sha256, role, relevance, summary) plus a
        retrieval_contract. No file contents are returned by this tool —
        bulk bytes must be fetched via `resources/read("scaffold://...")`.
        See `retrieval_contract` in the response for the full contract
        (metadata tools, bounded reads, and the compatibility fallback).

        NOTE: Utility scripts are NOT included. They are available via the
        mcp-base CLI: `pip install mcp-base && mcp-base --help`.

        Args:
            auth_type: Authentication type (default: "auth0"):
                       - "auth0": FastMCP Auth0Provider OAuth proxy
                       - "keycloak": FastMCP KeycloakAuthProvider (requires
                         Keycloak >= 26.6.0 and fastmcp >= 3.2.4)
                       - "oidc": Generic OIDC middleware for other IdPs
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

        # Register each artifact as a concrete MCP resource so it shows up
        # in `resources/list` and is directly addressable via
        # `resources/read`. Resource-first retrieval depends on this — the
        # URI-template handler in register_resources is just a fallback.
        project_id = result["project_id"]
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

        return result

    @mcp.tool(name="list_artifacts")
    async def list_artifacts(project_id: str) -> str:
        """
        List generated artifact paths and URIs (compact).

        Backwards-compatible path listing. For coordination metadata (role,
        relevance, symbols, notes), prefer `list_scaffold_artifact_metadata`.
        For bulk bytes, prefer `resources/read("scaffold://...")`.

        Args:
            project_id: The project identifier returned by generate_server_scaffold

        Returns:
            JSON with file paths and matching scaffold:// URIs.
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
            "artifact_uris": [
                {"path": path, "uri": f"scaffold://{project_id}/{path}"}
                for path, _ in artifacts
            ],
            "retrieval_contract": {
                "bulk_bytes": "resources/read('scaffold://{project_id}/{path}')",
                "metadata": "list_scaffold_artifact_metadata / read_scaffold_artifact_metadata",
                "fallback": "read_scaffold_artifact (context-bloat risk)",
            },
        }, indent=2)

    @mcp.tool(name="list_scaffold_artifact_metadata")
    async def list_scaffold_artifact_metadata(project_id: str) -> str:
        """
        Compact metadata for every artifact in a project (no contents).

        Intended to be the first tool called after generate_server_scaffold.
        Returns per-file:

        Universal fields:
        - path, uri, mime_type, size_bytes, sha256, hash_algorithm
        - content_encoding, line_endings, executable, permissions,
          post_write_actions
        - role, customization_relevance, summary,
          customization_notes, verification_notes

        Python-only module-level fields:
        - contains_business_logic, contains_registration, contains_helpers
        - primary_customization_surface
        - runtime_dependencies (human-readable list derived from imports)
        - exports (public top-level names)
        - registered_surface (functions decorated with @mcp.tool /
          @mcp.resource / @mcp.prompt inside register_* — the MCP runtime
          surface, lifted to module level for easy discovery)

        Python-only per-symbol fields (on each entry in `symbols`):
        - signature, decorators, line_hint, kind
        - summary, parameter_docs, returns_doc, raises, side_effects
        - usage_role (tool_implementation / tool_registration /
          resource_registration / prompt_registration / helper /
          context_adapter / admin_operation)
        - depends_on, required_context, intended_usage
        - exposed_as ({kind: tool|resource|prompt, name|uri: ...}) when
          the symbol is decorated for MCP exposure
        - methods (for classes) — same shape as top-level symbols

        The API surface is the materialization contract: it lets an agent
        import from and call into a scaffold module (e.g. `from
        mcp_context import with_mcp_context`) without ever pulling the
        file's bytes into model context.

        Args:
            project_id: Project ID from generate_server_scaffold.

        Returns:
            JSON {project_id, file_count, artifacts: [...]}
        """
        artifacts = artifact_store.list_project(project_id)
        if not artifacts:
            all_projects = artifact_store.list_all_projects()
            if all_projects:
                return (
                    f"Error: Project '{project_id}' not found.\n\n"
                    "Available projects:\n" + "\n".join(f"  - {p}" for p in all_projects)
                )
            return "Error: No artifacts stored. Call generate_server_scaffold first."

        records: List[Dict[str, Any]] = []
        for path, _ in artifacts:
            meta = build_artifact_metadata(
                project_id, path,
                include_symbols=True,
                include_imports=False,
            )
            if meta is None:
                continue
            # Strip project_id/path duplication at the envelope level.
            meta.pop("project_id", None)
            records.append(meta)

        return json.dumps({
            "project_id": project_id,
            "file_count": len(records),
            "artifacts": records,
        }, indent=2)

    @mcp.tool(name="read_scaffold_artifact_metadata")
    async def read_scaffold_artifact_metadata(project_id: str, path: str) -> str:
        """
        Detailed metadata for a single artifact (no file contents).

        Returns the same shape as list_scaffold_artifact_metadata plus,
        for Python files, an `imports` list (deduplicated top-level
        module imports). Every `symbols` entry carries the full
        materialization contract:

        - signature (full Python signature incl. defaults and annotations)
        - decorators, line_hint, summary
        - parameter_docs (per-arg prose from the docstring)
        - returns_doc (what the function returns conceptually)
        - raises (exception types declared in the docstring)
        - side_effects (detected from the body: logs, prompt reloads,
          blocking I/O, env reads, outbound HTTP, raises)
        - usage_role (tool_implementation vs tool_registration vs helper
          vs context_adapter vs admin_operation etc.)
        - depends_on (decorators and context types the symbol needs)
        - required_context (e.g. authenticated MCP request context)
        - intended_usage (how to invoke vs avoid)
        - exposed_as ({kind: tool|resource|prompt, name|uri}) when the
          symbol is decorated for MCP exposure
        - methods (classes) — same detail per method

        Module-level fields describe the file as a whole:
        contains_business_logic, contains_registration, contains_helpers,
        primary_customization_surface, runtime_dependencies,
        registered_surface, exports, imports.

        For most customization work, this metadata is enough to write
        calling code without loading the file bytes.

        Args:
            project_id: Project ID from generate_server_scaffold.
            path: File path within the project.
        """
        meta = build_artifact_metadata(
            project_id, path,
            include_symbols=True,
            include_imports=True,
        )
        if meta is None:
            available = artifact_store.list_project(project_id)
            if not available:
                all_projects = artifact_store.list_all_projects()
                if all_projects:
                    return (
                        f"Error: Project '{project_id}' not found.\n\n"
                        "Available projects:\n" + "\n".join(f"  - {p}" for p in all_projects)
                    )
                return "Error: No artifacts stored. Call generate_server_scaffold first."
            available_paths = [p for p, _ in available]
            return (
                f"Error: File '{path}' not found in project '{project_id}'.\n"
                f"Available files ({len(available_paths)}):\n"
                + "\n".join(f"  - {p}" for p in available_paths[:20])
                + ("\n  ..." if len(available_paths) > 20 else "")
            )
        return json.dumps(meta, indent=2)

    @mcp.tool(name="read_scaffold_artifact")
    async def read_scaffold_artifact(project_id: str, path: str) -> str:
        """
        ⚠️ LAST-RESORT COMPATIBILITY FALLBACK — DO NOT USE IF RESOURCES
        ARE AVAILABLE. ⚠️

        Reads the FULL content of a single scaffold artifact and returns
        it inside tool output, which pulls every byte into the model
        context window. For a typical scaffold (30+ files) this will
        blow the context budget and push other tool results out.

        The correct bulk-bytes path is ALWAYS:

            resources/read("scaffold://{project_id}/{path}")

        That path keeps artifact bytes out of model context entirely —
        the client writes them straight to disk. Use
        `list_scaffold_artifact_metadata` and
        `read_scaffold_artifact_metadata` for coordination data
        (compact, no file contents).

        Call this tool ONLY when the MCP client in use cannot invoke
        `resources/read` at all — e.g. OpenAI's `codex_apps` proxy,
        which forwards only tools and drops resources/prompts
        entirely. If your client supports `resources/read`, using this
        tool is a bug: switch to the resource path.

        RETRIEVAL GATE (see generate_server_scaffold instructions):
        If retrieval fails for ANY expected file — via any path — STOP.
        Do not reconstruct the file from memory, do not render templates as
        a substitute, do not create a placeholder. Produce a
        SCAFFOLD_RETRIEVAL_FAILURE.md report instead, per the failure
        template in the generate_server_scaffold response.

        Args:
            project_id: The project identifier returned by generate_server_scaffold
            path: File path within the project (e.g., "src/my_server.py").
                  Must match a path from the scaffold's `files` list exactly.

        Returns:
            On success: exact file content as stored at scaffold generation
            time.
            On not-found (project or path): a string starting with
            "Error: ..." describing the failure and listing available
            projects/files. Returning rather than raising avoids FastMCP
            logging a full traceback for an expected condition; treat the
            "Error: " prefix as a retrieval failure — do NOT fall back to
            template rendering.
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
                return (
                    f"Error: Project '{project_id}' not found. "
                    f"It may have expired.{hint}"
                )
            available_paths = [p for p, _ in available]
            return (
                f"Error: File '{path}' not found in project '{project_id}'.\n"
                f"Available files ({len(available_paths)}):\n"
                + "\n".join(f"  - {p}" for p in available_paths[:20])
                + ("\n  ..." if len(available_paths) > 20 else "")
            )
        return artifact.content
