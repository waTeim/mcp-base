"""
Test plugin for list_patterns tool.
"""
from plugins import TestPlugin, TestResult
import time


class TestListPatterns(TestPlugin):
    """Tests the list_patterns tool."""

    tool_name = "list_patterns"
    description = "Verifies list_patterns returns available pattern documentation"
    depends_on = []
    run_after = []

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            result = await session.call_tool("list_patterns", arguments={})

            # Extract text content from response
            if hasattr(result, 'content') and result.content:
                text_content = result.content[0].text if result.content else ""
            else:
                text_content = str(result)

            # Verify expected patterns
            expected_patterns = [
                "fastmcp-tools",
                "authentication",
                "kubernetes-integration",
                "helm-chart",
                "testing",
                "deployment"
            ]

            missing_patterns = [p for p in expected_patterns if p not in text_content]

            if missing_patterns:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing patterns: {missing_patterns}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=f"Found all {len(expected_patterns)} expected patterns",
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
