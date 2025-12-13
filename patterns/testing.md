# Testing Pattern

This document describes the testing pattern for MCP servers.

## Overview

MCP server testing uses a plugin-based architecture:

1. **Test Runner** - Discovers and executes test plugins
2. **Test Plugins** - Individual tool tests
3. **MCP Inspector** - Interactive manual testing
4. **Auth Proxy** - Simplifies authenticated testing

## Test Plugin Architecture

### Base Plugin Class

```python
from dataclasses import dataclass
from typing import Optional, List
from abc import ABC, abstractmethod
import time

@dataclass
class TestResult:
    """Result of a test execution."""
    plugin_name: str
    tool_name: str
    passed: bool
    message: str
    error: Optional[str] = None
    duration_ms: Optional[float] = None

class TestPlugin(ABC):
    """Base class for test plugins."""

    # Override these in subclasses
    tool_name: str = "unknown"
    description: str = "Test plugin"

    # Dependencies - tests that must pass before this one
    depends_on: List[str] = []

    # Soft dependencies - run after these if present
    run_after: List[str] = []

    def get_name(self) -> str:
        """Get the plugin name (class name by default)."""
        return self.__class__.__name__

    @abstractmethod
    async def test(self, session) -> TestResult:
        """
        Execute the test.

        Args:
            session: MCP ClientSession connected to server

        Returns:
            TestResult with pass/fail status
        """
        pass
```

### Example Test Plugin

```python
# test/plugins/test_list_resources.py
from plugins import TestPlugin, TestResult
import time

class TestListResources(TestPlugin):
    """Test the list_resources tool."""

    tool_name = "list_resources"
    description = "Lists all resources in namespace"
    depends_on = []  # No dependencies
    run_after = []

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            # Call the tool
            result = await session.call_tool(
                "list_resources",
                arguments={"namespace": "default"}
            )

            duration = (time.time() - start_time) * 1000

            # Check result
            if result and hasattr(result, 'content'):
                content = result.content[0].text if result.content else ""

                if "Error" in content:
                    return TestResult(
                        plugin_name=self.get_name(),
                        tool_name=self.tool_name,
                        passed=False,
                        message="Tool returned an error",
                        error=content,
                        duration_ms=duration
                    )

                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=True,
                    message=f"Successfully listed resources",
                    duration_ms=duration
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="No content in response",
                duration_ms=duration
            )

        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="Exception during test",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
```

### Test with Dependencies

```python
class TestCreateResource(TestPlugin):
    """Test creating a resource."""

    tool_name = "create_resource"
    description = "Creates a new resource"
    depends_on = ["TestListResources"]  # Must pass first
    run_after = []

    async def test(self, session) -> TestResult:
        # Implementation...
        pass

class TestDeleteResource(TestPlugin):
    """Test deleting a resource."""

    tool_name = "delete_resource"
    description = "Deletes a resource"
    depends_on = ["TestCreateResource"]  # Needs created resource
    run_after = []

    async def test(self, session) -> TestResult:
        # Implementation...
        pass
```

## Test Runner Pattern

### Plugin Discovery

```python
import importlib
import inspect
from pathlib import Path

def discover_plugins(plugins_dir: Path) -> List[TestPlugin]:
    """Discover all test plugins in directory."""
    plugins = []

    # Add to Python path
    sys.path.insert(0, str(plugins_dir.parent))

    for plugin_file in plugins_dir.glob("test_*.py"):
        module_name = f"plugins.{plugin_file.stem}"
        module = importlib.import_module(module_name)

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (hasattr(obj, 'test') and
                callable(obj.test) and
                obj.__module__ == module_name):
                plugins.append(obj())

    return plugins
```

### Topological Sort for Dependencies

```python
def topological_sort_plugins(plugins: List[TestPlugin]) -> List[TestPlugin]:
    """Sort plugins by dependencies."""
    plugin_map = {p.get_name(): p for p in plugins}
    visited = set()
    result = []

    def visit(plugin):
        if plugin.get_name() in visited:
            return
        visited.add(plugin.get_name())

        # Visit dependencies first
        for dep in plugin.depends_on + plugin.run_after:
            if dep in plugin_map:
                visit(plugin_map[dep])

        result.append(plugin)

    for plugin in plugins:
        visit(plugin)

    return result
```

### Test Execution

```python
async def run_plugin_tests(session, plugins: List[TestPlugin]) -> tuple[int, List[TestResult]]:
    """Run all plugin tests."""
    results = []
    failed_tests = set()

    for plugin in plugins:
        # Skip if dependencies failed
        deps_failed = [d for d in plugin.depends_on if d in failed_tests]
        if deps_failed:
            results.append(TestResult(
                plugin_name=plugin.get_name(),
                tool_name=plugin.tool_name,
                passed=False,
                message=f"Skipped: dependency failed: {deps_failed}"
            ))
            failed_tests.add(plugin.get_name())
            continue

        # Run test
        result = await plugin.test(session)
        results.append(result)

        if not result.passed:
            failed_tests.add(plugin.get_name())

    exit_code = 1 if failed_tests else 0
    return exit_code, results
```

## MCP Client Connection

### HTTP Transport

```python
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

async def connect_http(url: str, token: str = None):
    """Connect to MCP server via HTTP."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    mcp_url = f"{url}/mcp"

    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, get_session_id):
        async with ClientSession(read, write) as session:
            init_result = await session.initialize()
            print(f"Connected: {init_result.serverInfo.name}")

            # Run tests
            exit_code, results = await run_plugin_tests(session, plugins)
            return exit_code, results
```

## Auth Proxy for Testing

Simplify authenticated testing with a local proxy:

```python
# test/mcp-auth-proxy.py
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

class AuthProxyHandler(BaseHTTPRequestHandler):
    """Proxy that injects Authorization header."""

    def do_POST(self):
        # Read token from file
        token = Path("/tmp/mcp-user-token.txt").read_text().strip()

        # Forward request with auth header
        headers = dict(self.headers)
        headers["Authorization"] = f"Bearer {token}"

        response = requests.post(
            f"{BACKEND_URL}{self.path}",
            headers=headers,
            data=self.rfile.read(int(self.headers['Content-Length']))
        )

        # Return response
        self.send_response(response.status_code)
        for k, v in response.headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(response.content)
```

## Test Output Formats

### JSON Output

```python
def save_json_results(results: List[TestResult], output_file: str):
    """Save results as JSON."""
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed)
        },
        "tests": [
            {
                "plugin_name": r.plugin_name,
                "tool_name": r.tool_name,
                "passed": r.passed,
                "message": r.message,
                "error": r.error,
                "duration_ms": r.duration_ms
            }
            for r in results
        ]
    }

    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
```

### JUnit XML Output

```python
import xml.etree.ElementTree as ET

def save_junit_results(results: List[TestResult], output_file: str):
    """Save results as JUnit XML for CI/CD."""
    testsuite = ET.Element("testsuite", {
        "name": "MCP Automated Tests",
        "tests": str(len(results)),
        "failures": str(sum(1 for r in results if not r.passed))
    })

    for r in results:
        testcase = ET.SubElement(testsuite, "testcase", {
            "name": r.plugin_name,
            "classname": f"mcp.tools.{r.tool_name}",
            "time": f"{(r.duration_ms or 0) / 1000:.3f}"
        })

        if not r.passed:
            failure = ET.SubElement(testcase, "failure", {"message": r.message})
            if r.error:
                failure.text = r.error

    tree = ET.ElementTree(testsuite)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
```

## Test Runner CLI

```bash
# Run automated tests
./test-mcp.py --url https://mcp.example.com

# Save results
./test-mcp.py --url https://mcp.example.com --output results.json
./test-mcp.py --url https://mcp.example.com --output results.xml --format junit

# Use MCP Inspector for manual testing
./test-mcp.py --use-inspector --url https://mcp.example.com --use-proxy

# With kubectl port-forward
./test-mcp.py --use-inspector --port-forward --namespace mcp
```

## Best Practices

1. **One plugin per tool** - Keep tests focused
2. **Use dependencies** - Order tests logically
3. **Clean up after tests** - Delete created resources
4. **Include timing** - Track performance
5. **Support multiple outputs** - JSON for scripts, JUnit for CI
6. **Use auth proxy** - Simplifies authenticated testing
7. **Test error cases** - Verify error handling works
