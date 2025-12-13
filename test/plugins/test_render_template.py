"""
Test plugin for render_template tool.
"""
from plugins import TestPlugin, TestResult
import time


class TestRenderTemplate(TestPlugin):
    """Tests the render_template tool."""

    tool_name = "render_template"
    description = "Verifies render_template produces valid output"
    depends_on = []
    run_after = ["TestListTemplates"]

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            # Test rendering the entry point template
            result = await session.call_tool("render_template", arguments={
                "template_path": "server/entry_point.py.j2",
                "server_name": "Test MCP Server",
                "port": 9000,
                "default_namespace": "test-ns"
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
                    message="Template rendering failed",
                    error=text_content,
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify expected content in rendered output
            expected_content = [
                "#!/usr/bin/env python3",  # Shebang
                "test_mcp_server",  # Snake case name
                "9000",  # Port
            ]

            missing_content = [c for c in expected_content if c not in text_content]

            if missing_content:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing expected content: {missing_content}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message="Template rendered correctly with server_name='Test MCP Server'",
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
