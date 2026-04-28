"""
Test plugin for the list_artifacts tool.

Reuses the project_id published by TestGenerateServerScaffold (via
ctx.shared) so we don't pay the cost of generating a second scaffold.

Covers:
  - happy path (existing project_id)
  - error path (bogus project_id → "Available projects" hint)
"""
from plugins import TestPlugin, TestResult, TestContext
from typing import Optional
import json
import time


class TestListArtifacts(TestPlugin):
    tool_name = "list_artifacts"
    description = "Verifies list_artifacts returns paths + scaffold:// URIs"
    depends_on = ["TestGenerateServerScaffold"]
    run_after = ["TestGenerateServerScaffold"]

    async def test(self, session, ctx: Optional[TestContext] = None) -> TestResult:
        start_time = time.time()

        if ctx is None or "scaffold_project_id" not in ctx.shared:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="No scaffold_project_id in ctx.shared — depends on TestGenerateServerScaffold",
                duration_ms=(time.time() - start_time) * 1000,
            )

        project_id = ctx.shared["scaffold_project_id"]
        expected_artifacts = ctx.shared.get("scaffold_artifacts", [])
        expected_paths = {a["path"] for a in expected_artifacts}

        # Happy path
        try:
            result = await session.call_tool(
                "list_artifacts", arguments={"project_id": project_id},
            )
        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="list_artifacts call raised",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

        text = result.content[0].text if (
            hasattr(result, "content") and result.content
        ) else str(result)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="list_artifacts response is not JSON",
                error=text[:200],
                duration_ms=(time.time() - start_time) * 1000,
            )

        for key in ("project_id", "file_count", "files", "artifact_uris"):
            if key not in data:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"list_artifacts response missing '{key}'",
                    error=f"keys: {sorted(data.keys())}",
                    duration_ms=(time.time() - start_time) * 1000,
                )

        files = set(data["files"])
        if expected_paths and files != expected_paths:
            missing = expected_paths - files
            extra = files - expected_paths
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="list_artifacts paths don't match generate_server_scaffold manifest",
                error=f"missing={sorted(missing)} extra={sorted(extra)}",
                duration_ms=(time.time() - start_time) * 1000,
            )

        for entry in data["artifact_uris"]:
            if not entry["uri"].startswith(f"scaffold://{project_id}/"):
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"artifact_uris contains non-scaffold:// URI: {entry['uri']}",
                    duration_ms=(time.time() - start_time) * 1000,
                )

        # Negative path: bogus project_id should yield an error string,
        # not raise (the tool returns a string in both cases).
        bogus = "definitely-not-a-real-project-id-12345"
        try:
            err_result = await session.call_tool(
                "list_artifacts", arguments={"project_id": bogus},
            )
        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="list_artifacts(bogus) raised instead of returning an error string",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

        err_text = err_result.content[0].text if (
            hasattr(err_result, "content") and err_result.content
        ) else str(err_result)
        if "Error" not in err_text or bogus not in err_text:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="list_artifacts(bogus) did not return a recognizable error",
                error=err_text[:200],
                duration_ms=(time.time() - start_time) * 1000,
            )

        return TestResult(
            plugin_name=self.get_name(),
            tool_name=self.tool_name,
            passed=True,
            message=(
                f"list_artifacts: {data['file_count']} files for {project_id}; "
                f"bogus id rejected with error string"
            ),
            duration_ms=(time.time() - start_time) * 1000,
        )
