"""
Test plugin for listing prompts.
"""
from plugins import TestPlugin, TestResult
import time


class TestListPrompts(TestPlugin):
    """Tests the prompts/list endpoint."""

    tool_name = "list_prompts"
    description = "Verifies prompts/list works (currently no prompts defined)"
    depends_on = []
    run_after = []

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            result = await session.list_prompts()

            # Get list of prompts
            prompts = result.prompts if hasattr(result, 'prompts') else []

            # Currently mcp-base doesn't define any prompts, so list should be empty
            # This test verifies the endpoint works, even if empty
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=f"Prompts list returned successfully ({len(prompts)} prompts)",
                duration_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="Failed to list prompts",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
