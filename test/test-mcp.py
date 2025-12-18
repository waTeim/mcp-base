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
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


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


class LoggingSessionWrapper:
    """Wraps MCP session to log all requests and responses for debugging."""

    def __init__(self, session, log_file: str):
        self._session = session
        self._log_file = log_file
        self._request_counter = 0

        # Initialize log file
        with open(log_file, 'w') as f:
            f.write(f"# MCP Test Debug Log\n")
            f.write(f"# Started: {datetime.now().isoformat()}\n")
            f.write("=" * 80 + "\n\n")

    def _log_call(self, method: str, args: tuple, kwargs: dict, result: Any = None, error: Exception = None):
        """Log a method call with its arguments and result."""
        self._request_counter += 1
        timestamp = datetime.now().isoformat()

        with open(self._log_file, 'a') as f:
            f.write(f"\n{'=' * 100}\n")
            f.write(f"REQUEST #{self._request_counter}\n")
            f.write(f"{'=' * 100}\n")
            f.write(f"Time:   {timestamp}\n")
            f.write(f"Method: {method}\n")
            f.write(f"{'-' * 100}\n")

            # Log arguments
            if args or kwargs:
                f.write("ARGUMENTS:\n")
                f.write("-" * 100 + "\n")
                if args:
                    for i, arg in enumerate(args):
                        f.write(f"  Position {i}:\n")
                        f.write(self._format_value(arg, indent=4))
                if kwargs:
                    for key, value in kwargs.items():
                        f.write(f"  {key}:\n")
                        f.write(self._format_value(value, indent=4))

            # Log result or error
            if error:
                f.write("ERROR:\n")
                f.write("-" * 100 + "\n")
                f.write(f"{type(error).__name__}: {error}\n")
                import traceback
                f.write("\nTraceback:\n")
                f.write(traceback.format_exc())
            elif result is not None:
                f.write("RESPONSE:\n")
                f.write("-" * 100 + "\n")
                f.write(f"Type: {type(result).__name__}\n")
                f.write(self._format_value(result, indent=0))

            f.write("=" * 100 + "\n")

    def _format_value(self, value, indent=0):
        """Format a value for logging - NO TRUNCATION."""
        indent_str = " " * indent

        if hasattr(value, '__dict__'):
            # Object with attributes - show all attributes
            result = f"{indent_str}{type(value).__name__}:\n"
            attrs = {k: v for k, v in value.__dict__.items() if not k.startswith('_')}
            for key, val in attrs.items():
                result += f"{indent_str}  {key}: "
                result += self._format_value(val, indent + 4).lstrip()
            return result
        elif isinstance(value, (list, tuple)):
            if len(value) == 0:
                return f"[]\n"
            result = f"[{len(value)} items]\n"
            for i, item in enumerate(value):
                result += f"{indent_str}  [{i}]: "
                result += self._format_value(item, indent + 4).lstrip()
            return result
        elif isinstance(value, dict):
            if len(value) == 0:
                return f"{{}}\n"
            result = "\n"
            for key, val in value.items():
                result += f"{indent_str}  {key}: "
                result += self._format_value(val, indent + 4).lstrip()
            return result
        elif isinstance(value, str):
            # Multi-line strings get special formatting
            if '\n' in value:
                lines = value.split('\n')
                result = f"'''\n"
                for line in lines:
                    result += f"{indent_str}{line}\n"
                result += f"{indent_str}'''\n"
                return result
            else:
                return f"{value}\n"
        else:
            return f"{str(value)}\n"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    # Wrap common MCP session methods
    async def initialize(self, *args, **kwargs):
        try:
            result = await self._session.initialize(*args, **kwargs)
            self._log_call("initialize", args, kwargs, result=result)
            return result
        except Exception as e:
            self._log_call("initialize", args, kwargs, error=e)
            raise

    async def list_tools(self, *args, **kwargs):
        try:
            result = await self._session.list_tools(*args, **kwargs)
            self._log_call("list_tools", args, kwargs, result=result)
            return result
        except Exception as e:
            self._log_call("list_tools", args, kwargs, error=e)
            raise

    async def list_resources(self, *args, **kwargs):
        try:
            result = await self._session.list_resources(*args, **kwargs)
            self._log_call("list_resources", args, kwargs, result=result)
            return result
        except Exception as e:
            self._log_call("list_resources", args, kwargs, error=e)
            raise

    async def list_prompts(self, *args, **kwargs):
        try:
            result = await self._session.list_prompts(*args, **kwargs)
            self._log_call("list_prompts", args, kwargs, result=result)
            return result
        except Exception as e:
            self._log_call("list_prompts", args, kwargs, error=e)
            raise

    async def call_tool(self, *args, **kwargs):
        # Extract tool name for better logging
        tool_name = kwargs.get('name') or (args[0] if args else 'unknown')
        method_desc = f"call_tool({tool_name})"

        try:
            result = await self._session.call_tool(*args, **kwargs)
            self._log_call(method_desc, args, kwargs, result=result)
            return result
        except Exception as e:
            self._log_call(method_desc, args, kwargs, error=e)
            raise

    async def read_resource(self, *args, **kwargs):
        # Extract resource URI for better logging
        resource_uri = kwargs.get('uri') or (args[0] if args else 'unknown')
        method_desc = f"read_resource({resource_uri})"

        try:
            result = await self._session.read_resource(*args, **kwargs)
            self._log_call(method_desc, args, kwargs, result=result)
            return result
        except Exception as e:
            self._log_call(method_desc, args, kwargs, error=e)
            raise

    def __getattr__(self, name):
        """Forward other attributes to the wrapped session."""
        return getattr(self._session, name)


def get_user_token_interactive() -> Optional[str]:
    """
    Get user token by running get-user-token.py script.

    This will open a browser for Auth0 login and return the token.

    Returns:
        Access token or None if failed
    """
    print()
    print("=" * 70)
    print(Colors.blue("🔐 USER AUTHENTICATION REQUIRED"))
    print("=" * 70)
    print()
    print("The MCP server requires the 'openid' scope, which needs user login.")
    print("Running get-user-token.py to authenticate...")
    print()

    # Run get-user-token.py
    script_path = Path(__file__).parent / "get-user-token.py"

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=False,  # Let it interact with user
            text=True
        )

        if result.returncode != 0:
            print()
            print(Colors.red("❌ User authentication failed"))
            return None

        # Token should be saved to /tmp/user-token.txt
        token_file = Path("/tmp/user-token.txt")
        if token_file.exists():
            token = token_file.read_text().strip()
            print()
            print(Colors.green("✅ User token obtained successfully"))
            return token
        else:
            print()
            print(Colors.red("❌ Token file not found after authentication"))
            return None

    except Exception as e:
        print(Colors.red(f"❌ Error running get-user-token.py: {e}"))
        return None


def load_auth0_config(config_path: str = "auth0-config.json") -> Optional[Dict[str, Any]]:
    """Load Auth0 configuration from file."""
    config_file = Path(config_path)
    if not config_file.exists():
        return None

    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(Colors.yellow(f"Warning: Failed to load {config_path}: {e}"))
        return None


def get_token_from_auth0(config: Dict[str, Any]) -> Optional[str]:
    """
    Get an access token using user authentication (Authorization Code + PKCE).

    This simulates the same flow that Claude Desktop uses when connecting to the MCP server.

    Args:
        config: Auth0 configuration dictionary

    Returns:
        Access token or None if failed
    """
    # User authentication is required - same flow as Claude Desktop
    print(Colors.blue("Using user authentication (same as Claude Desktop)"))
    print()
    return get_user_token_interactive()


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


async def run_automated_tests(url: str, auth_token: str = None, output_file: str = None, output_format: str = "json", debug_log: str = None) -> int:
    """
    Run automated tests using plugin system.

    Args:
        url: HTTP URL for MCP server
        auth_token: Optional authentication token
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

    # Determine endpoint - use /test for Auth0 JWT token, /mcp for MCP token
    if '/test' in url:
        mcp_url = f"{url}/test" if not url.endswith(('/test', '/test/')) else url
    else:
        mcp_url = f"{url}/mcp" if not url.endswith(('/mcp', '/mcp/')) else url

    print(Colors.blue(f"Connecting to: {mcp_url}"))
    if auth_token:
        token_preview = f"{auth_token[:10]}...{auth_token[-10:]}" if len(auth_token) > 20 else auth_token
        print(Colors.blue(f"Authentication: Bearer Token ({token_preview})"))
    print()

    try:
        from mcp.client.streamable_http import streamablehttp_client
        from mcp.client.session import ClientSession

        # Prepare headers
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        async with streamablehttp_client(mcp_url, headers=headers) as (read, write, get_session_id):
            async with ClientSession(read, write) as raw_session:
                # Wrap session with logging if debug_log is specified
                if debug_log:
                    session = LoggingSessionWrapper(raw_session, debug_log)
                    print(Colors.blue(f"Debug logging enabled: {debug_log}"))
                else:
                    session = raw_session

                init_result = await session.initialize()
                print(Colors.green(f"Connected to server"))
                print(f"   Name: {init_result.serverInfo.name}")
                print(f"   Version: {init_result.serverInfo.version}")
                print()

                exit_code, results = await run_plugin_tests(session, plugins)

                if output_file:
                    save_test_results(results, output_file, output_format, url)

                if debug_log:
                    print()
                    print(Colors.green(f"Debug log saved to: {debug_log}"))

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
        '-t', '--token-file',
        dest='token_file',
        help='Path to file containing auth token (default: /tmp/user-token.txt)'
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
    parser.add_argument(
        '--debug-log',
        dest='debug_log',
        help='Save detailed request/response log for debugging (e.g., /tmp/mcp-debug.log)'
    )
    parser.add_argument(
        '--no-auth',
        action='store_true',
        help='Skip authentication (for testing against no-auth servers)'
    )

    args = parser.parse_args()

    # Get authentication token with priority:
    # 1. --no-auth flag skips all authentication
    # 2. Token file via --token-file
    # 3. Auto-obtain from auth0-config.json
    auth_token = None
    token_source = None

    if args.no_auth:
        print(Colors.yellow("⚠️  Running without authentication (--no-auth)"))
        print()
    elif args.token_file:
        token_path = Path(args.token_file)
        if not token_path.exists():
            print(Colors.red(f"❌ Token file not found: {args.token_file}"))
            print("   Run ./test/get-user-token.py to obtain a token")
            sys.exit(1)
        auth_token = token_path.read_text().strip()
        if not auth_token:
            print(Colors.red(f"❌ Token file is empty: {args.token_file}"))
            sys.exit(1)
        token_source = f"file: {args.token_file}"
        print(Colors.green(f"✅ Using token from: {token_source}"))
        print()
    else:
        # Try auto-obtain from auth0-config.json
        auth0_config = load_auth0_config("auth0-config.json")

        if auth0_config:
            print(Colors.green("✅ Found auth0-config.json"))
            print()
            auth_token = get_token_from_auth0(auth0_config)

            if auth_token:
                token_source = "user authentication (Authorization Code Flow)"
                print()
                print(Colors.green(f"✅ Using token from: {token_source}"))
                print()
            else:
                print()
                print(Colors.red("❌ Failed to obtain authentication token"))
                sys.exit(1)
        else:
            print(Colors.yellow("⚠️  No auth0-config.json found"))
            print("   Attempting connection without authentication...")
            print()

    exit_code = asyncio.run(run_automated_tests(
        url=args.url,
        auth_token=auth_token,
        output_file=args.output_file,
        output_format=args.output_format,
        debug_log=args.debug_log
    ))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
