"""
Test plugin for generate_server_scaffold tool.

Updated to handle new JSON return format.
"""
from plugins import TestPlugin, TestResult
import time
import json


class TestGenerateServerScaffold(TestPlugin):
    """Tests the generate_server_scaffold tool."""

    tool_name = "generate_server_scaffold"
    description = "Verifies scaffold generation produces complete project"
    depends_on = []
    run_after = ["TestRenderTemplate"]

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            # Test generating a server scaffold
            result = await session.call_tool("generate_server_scaffold", arguments={
                "server_name": "My Test Server"
            })

            # Extract content from response
            if hasattr(result, 'content') and result.content:
                text_content = result.content[0].text if result.content else ""
            else:
                text_content = str(result)

            # Parse JSON response
            try:
                data = json.loads(text_content)
            except json.JSONDecodeError:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Response is not valid JSON",
                    error=f"Got: {text_content[:200]}...",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify required fields in response
            required_fields = ["project_id", "server_name", "file_count", "files", "resource_links", "quick_start"]
            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing required fields: {missing_fields}",
                    error=f"Data: {data}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify expected files in files array
            # NOTE: bin/ scripts are no longer included in scaffold - they are in a separate package
            expected_files = [
                "src/my_test_server_server.py",  # Entry point
                "src/my_test_server_tools.py",   # Tools file
                "src/prompt_registry.py",         # Prompt management
                "Dockerfile",
                "requirements.txt",
                "Makefile",
                "chart/Chart.yaml",
                "chart/values.yaml",
                "chart/templates/prompts-configmap.yaml",  # Prompts ConfigMap
                "test/test-mcp.py",
                "test/plugins/__init__.py",
            ]

            files_list = data.get("files", [])
            missing_files = [f for f in expected_files if f not in files_list]

            if missing_files:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing expected files: {missing_files}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify resource_links structure
            if not isinstance(data.get("resource_links"), list):
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="resource_links is not a list",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify file_count matches files array
            if data.get("file_count") != len(files_list):
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"file_count ({data.get('file_count')}) doesn't match files array length ({len(files_list)})",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify quick_start is a list of strings
            quick_start = data.get("quick_start", [])
            if not isinstance(quick_start, list) or len(quick_start) == 0:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="quick_start should be a non-empty list",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=f"Scaffold generated successfully with all expected components (project_id: {data.get('project_id')})",
                duration_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="Tool call failed",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
