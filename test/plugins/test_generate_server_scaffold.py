"""
Test plugin for generate_server_scaffold tool.
"""
from plugins import TestPlugin, TestResult
import time


class TestGenerateServerScaffold(TestPlugin):
    """Tests the generate_server_scaffold tool."""

    tool_name = "generate_server_scaffold"
    description = "Verifies scaffold generation produces complete project"
    depends_on = []
    run_after = ["TestRenderTemplate"]

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            # Test generating a server scaffold (summary mode)
            # Use defaults to ensure the tool behaves correctly without explicit parameters
            result = await session.call_tool("generate_server_scaffold", arguments={
                "server_name": "My Test Server",
                "output_description": "summary"
            })

            # Extract text content from response
            if hasattr(result, 'content') and result.content:
                text_content = result.content[0].text if result.content else ""
            else:
                text_content = str(result)

            # Check for error message
            if text_content.startswith("Error"):
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Scaffold generation failed",
                    error=text_content,
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify expected files in summary
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
                # Bin scripts (Python only - no .sh allowed)
                "bin/add-user.py",
                "bin/create-secrets.py",
                "bin/make-config.py",
                "bin/setup-auth0.py",
                "bin/setup-rbac.py",
            ]

            missing_files = [f for f in expected_files if f not in text_content]

            if missing_files:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing expected files: {missing_files}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify Quick Start section
            if "Quick Start" not in text_content:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Missing Quick Start section in summary",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=f"Scaffold generated successfully with all expected components",
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
