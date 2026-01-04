"""
Test plugin for list_templates tool.
"""
from plugins import TestPlugin, TestResult
import time


class TestListTemplates(TestPlugin):
    """Tests the list_templates tool."""

    tool_name = "list_templates"
    description = "Verifies list_templates returns available templates"
    depends_on = []
    run_after = []

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            result = await session.call_tool("list_templates", arguments={})

            # Extract text content from response
            if hasattr(result, 'content') and result.content:
                text_content = result.content[0].text if result.content else ""
            else:
                text_content = str(result)

            # Verify expected content
            # NOTE: bin/ scripts are now in a separate package, so we only check core templates
            expected_sections = [
                "Server Templates",
                "Container Templates",
                "Helm Chart Templates",
                "Utility Templates",
                "Utility Scripts"  # Section noting scripts are in separate package
            ]

            expected_templates = [
                "entry_point.py.j2",
                "prompt_registry.py.j2",  # Versioned prompt management
                "Dockerfile.j2",
                "Chart.yaml.j2",
                "Makefile.j2",
            ]

            missing_sections = [s for s in expected_sections if s not in text_content]
            missing_templates = [t for t in expected_templates if t not in text_content]

            if missing_sections:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing sections: {missing_sections}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            if missing_templates:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing templates: {missing_templates}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=f"Found all expected sections and templates",
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
