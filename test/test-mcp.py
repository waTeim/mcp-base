#!/usr/bin/env python3
"""
MCP Base Server Test Runner

Tests the mcp-base server tools using the plugin system.
No authentication required for local testing.
"""

import os
import sys
import json
import argparse
import asyncio
import importlib
import inspect
from pathlib import Path
from typing import List


class Colors:
    """Colors for terminal output."""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

    @staticmethod
    def red(text): return f"{Colors.RED}{text}{Colors.NC}"
    @staticmethod
    def green(text): return f"{Colors.GREEN}{text}{Colors.NC}"
    @staticmethod
    def yellow(text): return f"{Colors.YELLOW}{text}{Colors.NC}"
    @staticmethod
    def blue(text): return f"{Colors.BLUE}{text}{Colors.NC}"


def topological_sort_plugins(plugins: List) -> List:
    """
    Sort plugins based on dependencies using topological sort.

    Args:
        plugins: List of plugin instances

    Returns:
        Sorted list of plugins (dependencies first)
    """
    plugin_map = {p.get_name(): p for p in plugins}
    visited = set()
    result = []

    def visit(plugin):
        if plugin.get_name() in visited:
            return
        visited.add(plugin.get_name())
        all_deps = list(set(plugin.depends_on + plugin.run_after))
        for dep_name in all_deps:
            if dep_name in plugin_map:
                visit(plugin_map[dep_name])
        result.append(plugin)

    for plugin in plugins:
        visit(plugin)

    return result


def discover_plugins(plugins_dir: Path) -> List:
    """Discover all test plugins in the plugins directory."""
    plugins = []

    if not plugins_dir.exists():
        return plugins

    sys.path.insert(0, str(plugins_dir.parent))

    for plugin_file in plugins_dir.glob("test_*.py"):
        try:
            module_name = f"plugins.{plugin_file.stem}"
            module = importlib.import_module(module_name)

            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (hasattr(obj, 'test') and
                    callable(obj.test) and
                    obj.__module__ == module_name):
                    plugins.append(obj())

        except Exception as e:
            print(Colors.yellow(f"Warning: Failed to load plugin {plugin_file.name}: {e}"))

    plugins = topological_sort_plugins(plugins)
    return plugins


async def run_plugin_tests(session, plugins: List) -> tuple[int, List]:
    """
    Run all plugin tests and report results.

    Returns:
        Tuple of (exit_code, results_list)
    """
    print("=" * 70)
    print("Running Tests")
    print("=" * 70)
    print()

    results = []
    passed = 0
    failed = 0
    failed_tests = set()

    for plugin in plugins:
        plugin_name = plugin.get_name()

        deps_failed = [dep for dep in plugin.depends_on if dep in failed_tests]
        if deps_failed:
            print(f"  {plugin_name}... ", end="")
            print(Colors.yellow(f"SKIPPED (dependency failed: {', '.join(deps_failed)})"))
            print()
            from plugins import TestResult
            results.append(TestResult(
                plugin_name=plugin_name,
                tool_name=plugin.tool_name,
                passed=False,
                message=f"Skipped because dependency failed: {', '.join(deps_failed)}"
            ))
            failed += 1
            failed_tests.add(plugin_name)
            continue

        print(f"  {plugin_name}...", end=" ", flush=True)

        try:
            result = await plugin.test(session)
            results.append(result)

            if result.passed:
                print(Colors.green("PASS"))
                passed += 1
            else:
                print(Colors.red("FAIL"))
                failed += 1
                failed_tests.add(plugin_name)

            if result.duration_ms:
                print(f"    Duration: {result.duration_ms:.1f}ms")
            print(f"    {result.message}")
            if result.error:
                print(Colors.red(f"    Error: {result.error}"))
            print()

        except Exception as e:
            print(Colors.red("EXCEPTION"))
            print(Colors.red(f"    Unexpected error: {e}"))
            print()
            failed += 1
            failed_tests.add(plugin_name)

            from plugins import TestResult
            results.append(TestResult(
                plugin_name=plugin_name,
                tool_name=plugin.tool_name,
                passed=False,
                message=f"Unexpected exception during test",
                error=str(e)
            ))

    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print()
    print(f"Total:  {passed + failed} tests")
    print(Colors.green(f"Passed: {passed}"))
    print(Colors.red(f"Failed: {failed}"))
    print()

    if failed == 0:
        print(Colors.green("All tests passed!"))
        exit_code = 0
    else:
        print(Colors.red(f"{failed} test(s) failed"))
        exit_code = 1

    return exit_code, results


def save_test_results(results: List, output_file: str, format: str = "json", url: str = None):
    """Save test results to a file."""
    from datetime import datetime, timezone

    if format == "json":
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "transport": "http",
            "url": url,
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "duration_ms": sum(r.duration_ms or 0 for r in results)
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

        print()
        print(Colors.green(f"Test results saved to: {output_file}"))

    elif format == "junit":
        import xml.etree.ElementTree as ET

        total = len(results)
        failures = sum(1 for r in results if not r.passed)
        duration_s = sum(r.duration_ms or 0 for r in results) / 1000.0

        testsuite = ET.Element("testsuite", {
            "name": "MCP Base Automated Tests",
            "tests": str(total),
            "failures": str(failures),
            "errors": "0",
            "time": f"{duration_s:.3f}",
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        })

        properties = ET.SubElement(testsuite, "properties")
        ET.SubElement(properties, "property", {"name": "transport", "value": "http"})
        if url:
            ET.SubElement(properties, "property", {"name": "url", "value": url})

        for r in results:
            testcase = ET.SubElement(testsuite, "testcase", {
                "name": r.plugin_name,
                "classname": f"mcp.tools.{r.tool_name}",
                "time": f"{(r.duration_ms or 0) / 1000:.3f}"
            })

            if not r.passed:
                failure = ET.SubElement(testcase, "failure", {
                    "message": r.message
                })
                if r.error:
                    failure.text = r.error

        tree = ET.ElementTree(testsuite)
        ET.indent(tree, space="  ")
        tree.write(output_file, encoding="utf-8", xml_declaration=True)

        print()
        print(Colors.green(f"Test results saved to: {output_file}"))


async def run_automated_tests(url: str, output_file: str = None, output_format: str = "json") -> int:
    """
    Run automated tests using plugin system.

    Args:
        url: HTTP URL for MCP server
        output_file: Path to save test results (optional)
        output_format: Format for saved results ('json' or 'junit')

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("=" * 70)
    print(Colors.blue("MCP Base Server - Automated Test Suite"))
    print("=" * 70)
    print()

    plugins_dir = Path(__file__).parent / "plugins"
    plugins = discover_plugins(plugins_dir)

    if not plugins:
        print(Colors.yellow("No test plugins found"))
        print(f"   Expected plugins in: {plugins_dir}")
        print()
        print("To create a test plugin, add a file like test/plugins/test_my_tool.py:")
        print("  from plugins import TestPlugin, TestResult")
        print("  class MyToolTest(TestPlugin):")
        print("      tool_name = 'my_tool'")
        print("      async def test(self, session): ...")
        return 1

    print(f"Discovered {len(plugins)} test plugin(s)")
    for plugin in plugins:
        print(f"  - {plugin.tool_name}: {plugin.description}")
    print()

    print(Colors.blue(f"Connecting to: {url}"))
    print()

    try:
        from mcp.client.streamable_http import streamablehttp_client
        from mcp.client.session import ClientSession

        # Construct MCP endpoint URL
        mcp_url = f"{url}/mcp" if not url.endswith(('/mcp', '/mcp/')) else url

        async with streamablehttp_client(mcp_url) as (read, write, get_session_id):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                print(Colors.green(f"Connected to server"))
                print(f"   Name: {init_result.serverInfo.name}")
                print(f"   Version: {init_result.serverInfo.version}")
                print()

                exit_code, results = await run_plugin_tests(session, plugins)

                if output_file:
                    save_test_results(results, output_file, output_format, url)

                return exit_code

    except ImportError as e:
        print(Colors.red(f"Failed to import MCP client library: {e}"))
        print()
        print("Install with: pip install mcp")
        return 1
    except Exception as e:
        print(Colors.red(f"Failed to connect to server: {e}"))
        import traceback
        traceback.print_exc()
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="MCP Base Server Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run tests against local server
  ./test-mcp.py --url http://localhost:8000

  # Save test results to JSON file
  ./test-mcp.py --url http://localhost:8000 --output results.json

  # Save test results to JUnit XML (for CI/CD)
  ./test-mcp.py --url http://localhost:8000 --output results.xml --format junit

Environment Variables:
  MCP_HTTP_URL    Default HTTP URL (default: http://localhost:8000)
"""
    )

    parser.add_argument(
        '-u', '--url',
        default=os.getenv('MCP_HTTP_URL', 'http://localhost:8000'),
        help='HTTP URL (default: http://localhost:8000 or $MCP_HTTP_URL)'
    )
    parser.add_argument(
        '-o', '--output',
        dest='output_file',
        help='Save test results to file'
    )
    parser.add_argument(
        '-f', '--format',
        dest='output_format',
        choices=['json', 'junit'],
        default='json',
        help='Output format for test results (default: json)'
    )

    args = parser.parse_args()

    exit_code = asyncio.run(run_automated_tests(
        url=args.url,
        output_file=args.output_file,
        output_format=args.output_format
    ))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
