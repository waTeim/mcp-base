"""
Test plugin for get_pattern tool.
"""
from plugins import TestPlugin, TestResult
import time


class TestGetPattern(TestPlugin):
    """Tests the get_pattern tool."""

    tool_name = "get_pattern"
    description = "Verifies get_pattern retrieves pattern documentation"
    depends_on = []
    run_after = ["TestListPatterns"]

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            # Test getting the fastmcp-tools pattern
            result = await session.call_tool("get_pattern", arguments={
                "name": "fastmcp-tools"
            })

            # Extract text content from response
            if hasattr(result, 'content') and result.content:
                text_content = result.content[0].text if result.content else ""
            else:
                text_content = str(result)

            # Check for error message
            if text_content.startswith("Error:"):
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Pattern retrieval failed",
                    error=text_content,
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify it looks like pattern documentation (markdown)
            if "#" not in text_content and len(text_content) < 100:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Pattern content doesn't look like documentation",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Test invalid pattern name
            invalid_result = await session.call_tool("get_pattern", arguments={
                "name": "nonexistent-pattern"
            })

            if hasattr(invalid_result, 'content') and invalid_result.content:
                invalid_text = invalid_result.content[0].text if invalid_result.content else ""
            else:
                invalid_text = str(invalid_result)

            if "Error:" not in invalid_text and "Unknown pattern" not in invalid_text:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Invalid pattern name did not return error",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message="Pattern retrieval works correctly",
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
