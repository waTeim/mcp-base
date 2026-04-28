"""
Test plugin for reading resources.

Covers the simple `template_path = ...; return template_path.read_text()`
handler bodies in mcp_base_tools.register_resources, plus the pattern://
and the additional template:// URIs that the original two plugins didn't
exercise.
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


class TestReadAllStaticResources(TestPlugin):
    """
    Reads every other registered template:// URI to exercise the trivial
    `read_text()` handler bodies in mcp_base_tools.register_resources.
    Each URI must return non-empty text content.
    """

    tool_name = "read_resource"
    description = "Verifies all template://* and remaining pattern://* URIs return non-empty content"
    depends_on = ["TestListResources"]
    run_after = ["TestReadPatternResource"]

    # URIs not already covered by TestReadTemplateResource / TestReadPatternResource.
    # Keep this list in sync with the @mcp.resource() decorators in
    # src/mcp_base_tools.py:register_resources.
    URIS = [
        "template://server/auth_fastmcp.py",
        "template://server/auth_oidc.py",
        "template://server/mcp_context.py",
        "template://server/user_hash.py",
        "template://server/tools.py",
        "template://server/prompt_registry.py",
        "template://container/Dockerfile",
        "template://container/requirements.txt",
        "template://helm/Chart.yaml",
        "template://helm/values.yaml",
        "template://Makefile",
        "pattern://generation-workflow",
        "pattern://architecture",
        "pattern://authentication",
        "pattern://kubernetes-integration",
        "pattern://helm-chart",
        "pattern://testing",
        "pattern://deployment",
        "pattern://prompt-management",
    ]

    async def test(self, session) -> TestResult:
        start_time = time.time()
        failures = []
        total_bytes = 0

        for uri in self.URIS:
            try:
                result = await session.read_resource(uri=uri)
            except Exception as e:
                failures.append(f"{uri}: {type(e).__name__}: {e}")
                continue

            if hasattr(result, "contents") and result.contents:
                text = result.contents[0].text or ""
            else:
                text = ""

            if not text.strip():
                failures.append(f"{uri}: empty content")
            else:
                total_bytes += len(text)

        duration_ms = (time.time() - start_time) * 1000
        if failures:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message=f"{len(failures)}/{len(self.URIS)} resource read(s) failed",
                error="\n".join(failures[:10]),
                duration_ms=duration_ms,
            )
        return TestResult(
            plugin_name=self.get_name(),
            tool_name=self.tool_name,
            passed=True,
            message=f"Read {len(self.URIS)} resources ({total_bytes} bytes total)",
            duration_ms=duration_ms,
        )
