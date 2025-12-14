"""
Test plugin for reading resources.
"""
from plugins import TestPlugin, TestResult
import time


class TestReadTemplateResource(TestPlugin):
    """Tests reading a template resource."""

    tool_name = "read_resource"
    description = "Verifies reading template://server/entry_point.py"
    depends_on = ["TestListResources"]
    run_after = []

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            result = await session.read_resource(uri="template://server/entry_point.py")

            # Extract text content
            if hasattr(result, 'contents') and result.contents:
                text_content = result.contents[0].text if result.contents else ""
            else:
                text_content = str(result)

            # Verify it's a Python file with expected content
            expected_markers = [
                "#!/usr/bin/env python3",
                "FastMCP",
                "def main():",
            ]

            missing = [m for m in expected_markers if m not in text_content]

            if missing:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Template missing expected content: {missing}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=f"Successfully read template ({len(text_content)} bytes)",
                duration_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="Failed to read template resource",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )


class TestReadPatternResource(TestPlugin):
    """Tests reading a pattern resource."""

    tool_name = "read_resource"
    description = "Verifies reading pattern://fastmcp-tools"
    depends_on = ["TestListResources"]
    run_after = ["TestReadTemplateResource"]

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            result = await session.read_resource(uri="pattern://fastmcp-tools")

            # Extract text content
            if hasattr(result, 'contents') and result.contents:
                text_content = result.contents[0].text if result.contents else ""
            else:
                text_content = str(result)

            # Verify it's a markdown document with expected content
            expected_markers = [
                "# FastMCP Tool Implementation Pattern",
                "@mcp.tool",
            ]

            missing = [m for m in expected_markers if m not in text_content]

            if missing:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Pattern missing expected content: {missing}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=f"Successfully read pattern ({len(text_content)} bytes)",
                duration_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="Failed to read pattern resource",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
