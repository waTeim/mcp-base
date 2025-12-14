"""
Test plugin for listing resources.
"""
from plugins import TestPlugin, TestResult
import time


class TestListResources(TestPlugin):
    """Tests the resources/list endpoint."""

    tool_name = "list_resources"
    description = "Verifies server exposes expected resources"
    depends_on = []
    run_after = []

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            result = await session.list_resources()

            # Get list of resource URIs (convert to strings for comparison)
            resource_uris = [str(r.uri) for r in result.resources] if hasattr(result, 'resources') else []

            # Expected resource URIs
            expected_template_resources = [
                "template://server/entry_point.py",
                "template://server/auth_fastmcp.py",
                "template://server/auth_oidc.py",
                "template://server/mcp_context.py",
                "template://server/user_hash.py",
                "template://server/tools.py",
                "template://container/Dockerfile",
                "template://container/requirements.txt",
                "template://helm/Chart.yaml",
                "template://helm/values.yaml",
                "template://Makefile",
            ]

            expected_pattern_resources = [
                "pattern://fastmcp-tools",
                "pattern://authentication",
                "pattern://kubernetes-integration",
                "pattern://helm-chart",
                "pattern://testing",
                "pattern://deployment",
            ]

            expected_resources = expected_template_resources + expected_pattern_resources

            # Check for missing resources
            missing = [r for r in expected_resources if r not in resource_uris]

            if missing:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing {len(missing)} resource(s): {missing[:3]}...",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=f"Found all {len(expected_resources)} expected resources",
                duration_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="Failed to list resources",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
