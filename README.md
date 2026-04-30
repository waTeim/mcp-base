# mcp-base

An MCP server that helps AI agents build production-ready MCP servers for
Kubernetes environments. Exposes templates, patterns, and tools via the
[Model Context Protocol](https://modelcontextprotocol.io/) so an agent can
scaffold a complete project (server code, tests, Helm chart, container
build) in one tool call and customize it locally.

There are **two distinct workflows** documented here:

- [**A. Use mcp-base to generate a new MCP server**](#workflow-a--use-mcp-base-to-generate-a-new-mcp-server) — the typical path: an agent calls `generate_server_scaffold`, retrieves files via `resources/read`, customizes the tools module, writes tests, and deploys.
- [**B. Work on mcp-base itself**](#workflow-b--work-on-mcp-base-itself) — for contributors. Same Makefile / coverage / port-forward harness as a generated project, because mcp-base dogfoods its own templates.

The two workflows share concepts. The [Shared concepts](#shared-concepts)
section below describes them once.

---

## Shared concepts

### Canonical project config (`mcp-project.yaml`)

Every project — mcp-base itself and every server generated from it — has a
single `mcp-project.yaml` at the repo root that is the source of truth for
build and deployment defaults:

```yaml
project:
  name: my-server
  chartName: my-server
ports:
  main: 4200      # production server port
  test: 4201      # no-auth test sidecar port
build:
  registry: ghcr.io/your-org
  imageName: my-server
  testImageName: my-server-test
  tag: latest
  platform: linux/amd64
  containerTool: docker
deployment:
  helmRelease: my-server
  namespace: default
  serviceType: ClusterIP
  testSidecarEnabled: true
```

Everything downstream derives from this file:

```
mcp-project.yaml
   │
   │  python bin/sync-config.py
   ▼
make.env  ──►  Makefile (REGISTRY, IMAGE_NAME, HELM_RELEASE, MCP_PORT, ...)
   │
   ▼
test/test-mcp.py reads ports.* directly for --url / --local-port defaults
chart/values.yaml carries the chart's *defaults* (matching ports.*)
<helmRelease>.yaml at repo root is the per-release values overlay,
   passed to helm via `-f $(HELM_VALUES_FILE)`. NOT generated — edit directly.
```

Edit `mcp-project.yaml`, run `python bin/sync-config.py` (or `make config`),
and every other artifact stays consistent. Don't hand-edit `make.env`.

### No-auth test sidecar

The Helm chart deploys a sidecar container that runs the test server with
`--no-auth`, exposed at `/test` over ClusterIP only (never via Ingress).
The sidecar runs a *separate* test image — built by `make build-test`
`FROM` the production image, with the `*_test_server.py` entrypoint added.
The chart auto-derives the test image repository from the main image by
replacing the trailing `-server` suffix with `-test-server`.

A mock identity (`sub`, `iss`) is injected by `NoAuthMiddleware`, so tools
that depend on `MCPContext.user_id` keep working. The production server
(`/mcp`) still requires real OIDC.

### Resource-first scaffold retrieval

`generate_server_scaffold` returns a *manifest* — `project_id`, `artifacts`
(path + URI + sha256 + metadata), `retrieval_contract`, `workflow`. Bulk
file bytes flow through `resources/read("scaffold://<id>/<path>")` so they
stay out of model context. Each on-disk file must hash-match the manifest;
on any retrieval failure, the agent stops and writes
`SCAFFOLD_RETRIEVAL_FAILURE.md` rather than reconstructing or substituting.

### Required tests

Every `@mcp.tool` you add must have a corresponding plugin under
`test/plugins/test_<your_tool>.py` covering both a happy path and at least
one error path. The scaffold ships `test/plugins/test_example.py` as a
heavily-commented starter — copy it per tool. See
[`patterns/testing.md`](patterns/testing.md) for the full contract.

---

## Workflow A — Use mcp-base to generate a new MCP server

This is the path agents use. The mcp-base server has to be running
somewhere the agent's MCP client can reach — locally for development or
deployed to the cluster.

### 1. Connect to mcp-base

The simplest path is to run mcp-base locally and point Claude Desktop /
Codex / your agent at it:

```bash
git clone https://github.com/your-org/mcp-base.git
cd mcp-base
pip install -r requirements.txt
python src/mcp_base_server.py --port 4200
```

Add to your MCP client's config:

```json
{
  "mcpServers": {
    "mcp-base": { "url": "http://localhost:4200/mcp" }
  }
}
```

### 2. Generate the scaffold

Ask the agent (or call the tool directly):

> Use mcp-base to generate an MCP server called "My Kubernetes Manager"
> that manages pods.

The agent will:

1. Call `generate_server_scaffold(server_name="My Kubernetes Manager")` →
   gets a manifest of ~40 files.
2. For each artifact: read bytes via `resources/read("scaffold://...")`,
   write to disk, verify sha256 matches the manifest entry.
3. Stop and emit `SCAFFOLD_RETRIEVAL_FAILURE.md` if any hash mismatches —
   never reconstruct from memory.

### 3. Configure

Edit the canonical project config first. The defaults baked into
`mcp-project.yaml` are placeholders:

```bash
$EDITOR mcp-project.yaml          # set registry, image names, namespace, ports
$EDITOR <helmRelease>.yaml        # release values overlay (image.repository,
                                   # ingress, OIDC issuer/audience, ...)
```

### 4. Customize tools

Add `@mcp.tool` / `@mcp.resource` / `@mcp.prompt` implementations to
`src/<server>_tools.py`. The scaffold ships standard plugins for
list_resources / read_resource / list_prompts / health endpoints; extend
them only when your server's resource surface changes.

### 5. Write tests (required)

For every new tool, copy `test/plugins/test_example.py` to
`test/plugins/test_<your_tool>.py`. Adapt the body — happy path AND at
least one error path. Run:

```bash
make dev-deps        # one-time: pip install -r test/requirements.txt
make test            # starts the no-auth server, runs the plugin suite, stops it
make dev-run-test    # optional: manual no-auth test server for debugging
make dev-coverage    # full pipeline under coverage.py with line/branch report
```

Confirm the lines you added show up as covered before declaring the tool
done. See [`patterns/testing.md`](patterns/testing.md) for the contract,
the gotchas (`AnyUrl` → `str`, `result.contents` vs `result.content`,
returning error strings vs raising), and the customization checklist.

### 6. Deploy

```bash
make build           # docker build with $(IMAGE_FULL) tag
make build-test      # docker build of the test image (FROM main image)
make push            # push main image
make push-test       # push test image
make helm-install    # helm upgrade --install with -f <release>.yaml
```

Helm install does **not** pass `--create-namespace` (assumes cluster-admin
rights you may not have) or `--wait` (blocks on crashing sidecars and
hides them). Pre-create the namespace if needed; check with `make k8s-pods`.

### 7. Test the deployed server

```bash
make test-cluster        # auto kubectl port-forward → /test on the no-auth sidecar
```

The target port-forwards to the no-auth test sidecar using values derived
from `mcp-project.yaml` through `make.env`. To test an authenticated endpoint,
run `test/test-mcp.py` manually with `--token-file` and an explicit URL or
port-forward.

---

## Workflow B — Work on mcp-base itself

For contributors. mcp-base dogfoods every pattern it teaches: it has its
own `mcp-project.yaml`, its own `bin/sync-config.py`, the same Makefile /
coverage / port-forward harness, the same chart structure.

### Setup

```bash
git clone https://github.com/your-org/mcp-base.git
cd mcp-base
pip install -r requirements.txt
pip install -r test/requirements.txt   # coverage, httpx for the test harness
```

### Run locally

```bash
# Production (auth-enforcing) server:
python src/mcp_base_server.py --port 4200

# OR no-auth test server (for local testing without OIDC setup):
python src/mcp_base_test_server.py --no-auth --port 4201
```

### Make changes

Most customization happens in two places:

- `src/mcp_base_tools.py` — the tools, resources, and pattern registry.
  Adding a new tool here means updating both `register_tools` and the
  artifact metadata role registry at the top of the file (so generated
  scaffolds get sensible `customization_relevance` / role hints).
- `templates/` — the Jinja templates that ship in every generated
  scaffold. Editing `templates/Makefile.j2`, `templates/test/`, or
  `templates/helm/` reshapes what every newly-generated project gets.

### Test

```bash
make test            # plugin suite against http://localhost:4201/test
make dev-coverage    # full pipeline under coverage.py
make dev-coverage-html
```

The plugin suite covers the actual tools mcp-base exposes
(`generate_server_scaffold`, `list_artifacts`, `read_scaffold_artifact`,
`render_template`, `list_templates`, `list_patterns`, etc.). New tools
should ship with new plugins under `test/plugins/`.

When working on Jinja templates, regenerate a smoke scaffold to confirm
the rendered output is valid Python / valid YAML:

```bash
python -c "
import asyncio, ast, sys
sys.path.insert(0, 'src')
from mcp_base_tools import generate_server_scaffold_impl
from artifact_store import artifact_store
async def main():
    res = await generate_server_scaffold_impl(server_name='Smoke Test')
    pid = res['project_id']
    for a in res['artifacts']:
        if a['path'].endswith('.py'):
            ast.parse(artifact_store.get(pid, a['path']).content)
    print(f'OK: {res[\"file_count\"]} files all parse')
asyncio.run(main())
"
```

### Configure + deploy

mcp-base itself can be deployed to a cluster as an MCP server (so a
hosted Claude can use it). The workflow is the same as Workflow A:

```bash
$EDITOR mcp-project.yaml      # registry, image names, namespace, ports
python bin/sync-config.py     # regenerate make.env
$EDITOR mcp-base.yaml         # release values overlay (already exists)
make build && make build-test
make push  && make push-test
make helm-install             # uses -f mcp-base.yaml
make test-cluster             # smoke against the deployed test sidecar
```

For OIDC setup, see [`patterns/authentication.md`](patterns/authentication.md)
and [`docs/KEYCLOAK-HOWTO.md`](docs/KEYCLOAK-HOWTO.md).

---

## Reference

- [`docs/workflows.md`](docs/workflows.md) — deeper reference for both workflows: dataflow diagrams, smoke-test snippets, "how do I change …" cheatsheet
- [`patterns/generation-workflow.md`](patterns/generation-workflow.md) — full agent workflow for generating a server (read this if you're an agent using mcp-base)
- [`patterns/testing.md`](patterns/testing.md) — test plugin contract, ctx.shared coordination, coverage workflow, what every new tool must cover
- [`patterns/fastmcp-tools.md`](patterns/fastmcp-tools.md) — implementing tools with `@with_mcp_context`, `MCPContext`, error-string convention
- [`patterns/authentication.md`](patterns/authentication.md) — Pattern A (Auth0/OIDC proxy) vs Pattern B (Keycloak DCR) split
- [`patterns/helm-chart.md`](patterns/helm-chart.md) — chart structure, test sidecar derivation, RBAC bindings
- [`patterns/deployment.md`](patterns/deployment.md) — Kubernetes deployment, the `--create-namespace` / `--wait` rationale
- [`patterns/prompt-management.md`](patterns/prompt-management.md) — versioned prompts with ConfigMap hot-reload
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — internals: artifact store, Jinja env, scaffold metadata pipeline
- [`CLAUDE.md`](CLAUDE.md) — guidance for Claude Code working in this repo
- [`docs/cli-integration-contract.md`](docs/cli-integration-contract.md) — schemas for `mcp-base` CLI artifacts (`oidc-config.json`, etc.)

## License

See [LICENSE](LICENSE).
