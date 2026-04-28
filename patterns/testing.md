# Testing Pattern

How to test the MCP server you just generated, and — critically — how to
**add tests for every tool you implement** in
`src/<server>_tools.py`. The harness is designed to make that step
mechanical.

---

## TL;DR for agents customizing a generated server

For each new `@mcp.tool` you add to `src/<server>_tools.py`, you MUST
add a corresponding plugin under `test/plugins/test_<your_tool>.py`.

1. Copy `test/plugins/test_example.py` to `test/plugins/test_<your_tool>.py`.
2. Rename the class to `Test<YourToolPascalCase>`.
3. Set `tool_name` to the exact string you passed to `@mcp.tool(name="...")`.
4. Replace the body with **happy-path** + at least one **error-path**
   assertion against the contract you documented in your tool's
   docstring.
5. Run `make dev-coverage` locally to confirm the new lines are
   exercised.

The starter file `test/plugins/test_example.py` has a dense
header comment walking through each step — open it before adapting.

---

## Architecture

```
test/
├── Dockerfile                   # test sidecar image (FROM main image, --no-auth)
├── test-mcp.py                  # plugin runner; --no-auth and --port-forward modes
├── run-coverage.py              # spawns server under coverage, runs runner, reports
├── requirements.txt             # test-only deps (coverage, httpx)
└── plugins/
    ├── __init__.py              # TestPlugin / TestResult / TestContext
    ├── test_list_resources.py   # standard: resources/list
    ├── test_read_resource.py    # standard: resources/read
    ├── test_list_prompts.py     # standard: prompts/list
    ├── test_health_endpoints.py # standard: GET /healthz, /readyz
    ├── test_example.py          # ← STARTER — copy per new tool
    └── test_<your_tool>.py      # ← write one per @mcp.tool you add
```

Two ways to run:

```bash
# Local, against a no-auth test server you spawn:
make dev-run-test          # in one terminal
make test                  # in another

# In-cluster (auto kubectl port-forward to the test sidecar):
make test-cluster

# Local, under coverage:
make dev-deps              # one-time: pip install -r test/requirements.txt
make dev-coverage          # spawns test server under coverage, runs tests, reports
make dev-coverage-html     # also writes coverage-html/index.html
```

---

## Plugin contract

```python
from plugins import TestPlugin, TestResult, TestContext
from typing import Optional
import time

class TestMyTool(TestPlugin):
    tool_name = "my_tool"                          # MUST match @mcp.tool(name=...)
    description = "Verifies my_tool round-trips X"
    depends_on  = []                               # hard: failure cascades
    run_after   = []                               # soft: ordering only

    async def test(self, session, ctx: Optional[TestContext] = None) -> TestResult:
        start = time.time()
        result = await session.call_tool("my_tool", arguments={"x": 1})
        text = result.content[0].text if (
            hasattr(result, "content") and result.content
        ) else str(result)
        # ... assertions ...
        return TestResult(
            plugin_name=self.get_name(),
            tool_name=self.tool_name,
            passed=True,
            message="...",
            duration_ms=(time.time() - start) * 1000,
        )
```

### Two valid signatures

The runner inspects each plugin's `test()` signature and only passes
`ctx` if the parameter is declared:

| Signature | When to use |
|-----------|-------------|
| `async def test(self, session)` | Pure MCP-protocol tests with no need for cross-plugin state or non-MCP HTTP. |
| `async def test(self, session, ctx: Optional[TestContext] = None)` | Need `ctx.base_url` (for `/healthz`-style plain-HTTP tests) or `ctx.shared` (for cross-plugin coordination). |

### `TestContext`

```python
@dataclass
class TestContext:
    base_url: str                   # e.g. "http://127.0.0.1:8001/test"
    shared:   Dict[str, Any] = field(default_factory=dict)
```

- `base_url` — the MCP endpoint the runner connected to. For non-MCP HTTP
  endpoints (`/healthz`, `/readyz`, `/metrics`, …) strip the path and
  rebuild: see `_strip_path` in `test/plugins/test_health_endpoints.py`.
- `shared` — a per-run scratch dict. Earlier plugins publish, later
  plugins read. Use `depends_on` / `run_after` to enforce ordering.

### Ordering: `depends_on` vs `run_after`

```python
depends_on = ["TestCreateResource"]   # hard — skipped if TestCreateResource fails
run_after  = ["TestListResources"]    # soft — runs even if TestListResources fails
```

Both reference plugin **class names**. The runner topologically sorts
across both edges.

### Cross-plugin state via `ctx.shared`

```python
# In a "create" plugin:
ctx.shared.setdefault("created_clusters", []).append(cluster_name)

# In a "delete" plugin (depends_on=["TestCreateCluster"]):
for name in ctx.shared.get("created_clusters", []):
    await session.call_tool("delete_cluster", arguments={"name": name})
```

This is the supported way to thread fixture state. Don't use module
globals — they leak between test runs.

---

## What every new tool's test must cover

For each `@mcp.tool` in `src/<server>_tools.py`, your plugin MUST
verify both:

1. **Happy path** — valid inputs, assert response **shape** (specific
   keys for JSON tools; distinctive substrings for prose tools). "No
   exception" is not enough — a tool returning the wrong content with a
   200 still breaks consumers.
2. **At least one error path** — invalid inputs (bad namespace, missing
   resource, empty argument) should produce a recognizable error
   *response*, not an unhandled exception. Both shapes count:
   - The tool returns an `"Error: ..."` string (preferred — no
     server-side traceback).
   - The MCP response carries `isError=True` with the message in the
     content.

For tools with side effects (create/update/delete K8s resources), also
write a follow-up plugin that **observes** the side effect — list, get,
or describe. Pair them via `depends_on` so the observer is skipped if
the create failed.

For tools that return large output, assert size is bounded. Runaway
output crowds out other tool results in model context.

### Detecting operational errors

Many tools return success at the MCP protocol layer but the underlying
operation failed (e.g. RBAC 403). Use the helper from `plugins`:

```python
from plugins import check_for_operational_error
is_err, msg = check_for_operational_error(text)
if is_err:
    return TestResult(... passed=False, error=msg ...)
```

It catches Kubernetes-style errors (`is forbidden:`, `Permission denied`,
`Connection refused`, etc.).

---

## Critical gotchas

### `result.uri` is `AnyUrl`, not `str`

```python
result = await session.list_resources()
uris = [str(r.uri) for r in result.resources]   # ← str() is required
```

Without `str()`, comparisons against string URIs silently fail.

### `result.contents` vs `result.content`

- `read_resource()` returns `ReadResourceResult` with `.contents` (plural).
- `call_tool()` returns `CallToolResult` with `.content` (singular).

Defensive pattern:

```python
text = result.content[0].text if (
    hasattr(result, "content") and result.content
) else str(result)
```

### Tool error reporting

Tools should `return "Error: ..."` strings rather than `raise ValueError`.
Raising triggers FastMCP's traceback-formatting logger, which dumps a
Rich panel to stderr — noisy and easy to confuse with real bugs. Both
shapes are valid; the example plugin handles both.

---

## Coverage workflow

```
make dev-deps           # pip install -r test/requirements.txt (one-time)
make dev-coverage       # full cycle: spawn test server under coverage,
                        # run plugin suite, SIGTERM, combine, report
make dev-coverage-html  # same + HTML report at coverage-html/index.html
```

`test/run-coverage.py` orchestrates:

1. Picks a free local port.
2. Spawns the test server via `python -m coverage run`.
3. Waits for the port to bind.
4. Runs `test/test-mcp.py --no-auth --url http://127.0.0.1:<port>/test`.
5. Sends `SIGTERM` — caught by `_install_clean_shutdown_handlers()` in
   the test server, which calls `sys.exit(0)` so atexit fires and
   coverage flushes its data file.
6. `coverage combine` merges the parallel-mode files.
7. `coverage report` (and optionally `coverage html`).

The `_install_clean_shutdown_handlers` step is load-bearing — uvicorn
restores signal handlers on shutdown and re-raises the captured signal,
so the handler we install BEFORE `uvicorn.run()` is what eventually
executes. Without it the process exits with 128+sig and atexit is
skipped → no coverage data.

### Reading the report

```
Name                         Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------
src/<server>_tools.py          734     80    298     43  86.1%   ...
src/<server>_test_server.py    144     20     28      4  83.7%   ...
```

The `Missing` column lists line numbers (and `start->end` branch arcs)
for code your tests didn't reach. **Before merging a new tool: confirm
the lines you added show up as covered.** If your new tool's body is
in `Missing`, your test is calling something else.

### Setting an expectation

A good rule of thumb after the first iteration of a tool:

- The happy-path lines of the tool body: **100% covered**.
- The error branches inside the tool: **at least one per branch covered**.
- Helper functions: covered transitively if they're on the hot path.

Anything below 80% on a hand-written tool means a missing test.

---

## Health endpoints

`/healthz` (`{"status": "alive"}`) and `/readyz` (`{"status": "ready"}`)
are the chart's K8s probe surface. The standard
`test_health_endpoints.py` plugin hits them via httpx (deriving the URL
from `ctx.base_url`) and asserts both status code and JSON body. Don't
delete it — silent regressions here mean broken pod health checks in
production.

---

## In-cluster testing

The Helm chart enables a sidecar container that runs the test server in
`--no-auth` mode behind ClusterIP only (never via Ingress). To test
against it:

```bash
make test-cluster
# Equivalent to:
# python test/test-mcp.py --no-auth --port-forward <release>
```

`--port-forward [namespace/]service[:port]` spawns and tears down
`kubectl port-forward` automatically. Namespace defaults to the current
kubectl context's namespace; port defaults to the test sidecar port.

The mock identity (`sub`, `iss`) is injected by `NoAuthMiddleware` so
tools that rely on `MCPContext.user_id` keep working.

---

## Output formats

```bash
./test/test-mcp.py --output results.json                 # JSON
./test/test-mcp.py --output results.xml --format junit   # JUnit XML for CI
```

JUnit format integrates with GitHub Actions, GitLab CI, Jenkins.

---

## Best practices recap

1. **One plugin per tool.** Don't pack multiple unrelated tools into one plugin.
2. **Always write a negative test.** Happy-path-only tests miss bad-input regressions.
3. **Clean up after side-effecting tests.** A `Test<X>Delete` plugin with `depends_on=["Test<X>Create"]`.
4. **Use `ctx.shared` for fixture state.** Never module globals.
5. **Convert Pydantic types.** `str(r.uri)` for AnyUrl comparisons.
6. **Match real content.** Substring checks must match what the file/tool actually returns.
7. **Run `make dev-coverage` before declaring a tool done.** New code should show up in the report as covered.
8. **Test the K8s probe endpoints.** `test_health_endpoints.py` ships pre-wired; don't remove it.
