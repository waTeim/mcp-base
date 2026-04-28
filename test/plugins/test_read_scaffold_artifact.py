"""
Test plugin for the read_scaffold_artifact tool (LAST-RESORT fallback path).

The preferred retrieval path is resources/read("scaffold://...") which keeps
bytes out of model context. read_scaffold_artifact returns full file
content inside tool output and exists for tool-only clients (e.g. OpenAI's
codex_apps proxy). We test it because real clients use it, the bytes need
to match the manifest's sha256, and the error branches matter.

Reuses the project_id published by TestGenerateServerScaffold.

Covers:
  - happy path: read a known artifact, verify sha256 matches manifest
  - error path: bogus path under valid project_id
  - error path: bogus project_id
"""
from plugins import TestPlugin, TestResult, TestContext
from typing import Optional
import hashlib
import time


def _content_text(result) -> str:
    if hasattr(result, "content") and result.content:
        return result.content[0].text or ""
    return str(result)


class TestReadScaffoldArtifact(TestPlugin):
    tool_name = "read_scaffold_artifact"
    description = "Verifies read_scaffold_artifact returns exact bytes (sha256-matched) and rejects bad keys"
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
        artifacts = ctx.shared.get("scaffold_artifacts") or []
        if not artifacts:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="ctx.shared['scaffold_artifacts'] empty",
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Pick a deterministic, small text file we know is in every scaffold.
        target = next(
            (a for a in artifacts if a["path"] == "Dockerfile"),
            artifacts[0],
        )
        target_path = target["path"]
        expected_sha = target["sha256"]

        # Happy path
        try:
            result = await session.call_tool(
                "read_scaffold_artifact",
                arguments={"project_id": project_id, "path": target_path},
            )
        except Exception as e:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="read_scaffold_artifact call raised",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

        content = _content_text(result)
        actual_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual_sha != expected_sha:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message=f"sha256 mismatch on {target_path}",
                error=f"expected={expected_sha} got={actual_sha} bytes={len(content)}",
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Error path: bad path under valid project
        bad_path = "src/this/file/does/not/exist.py"
        try:
            err1 = await session.call_tool(
                "read_scaffold_artifact",
                arguments={"project_id": project_id, "path": bad_path},
            )
            err1_text = _content_text(err1)
            err1_signaled = (
                getattr(err1, "isError", False)
                or "not found" in err1_text.lower()
            )
        except Exception as e:
            err1_signaled = "not found" in str(e).lower() or "ValueError" in str(e)
            err1_text = str(e)
        if not err1_signaled:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message=f"bad path was accepted instead of producing 'not found'",
                error=err1_text[:200],
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Error path: bogus project_id
        bogus = "no-such-project-id-12345"
        try:
            err2 = await session.call_tool(
                "read_scaffold_artifact",
                arguments={"project_id": bogus, "path": "Dockerfile"},
            )
            err2_text = _content_text(err2)
            err2_signaled = (
                getattr(err2, "isError", False)
                or "not found" in err2_text.lower()
            )
        except Exception as e:
            err2_signaled = "not found" in str(e).lower() or "ValueError" in str(e)
            err2_text = str(e)
        if not err2_signaled:
            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=False,
                message="bogus project_id was accepted instead of producing 'not found'",
                error=err2_text[:200],
                duration_ms=(time.time() - start_time) * 1000,
            )

        return TestResult(
            plugin_name=self.get_name(),
            tool_name=self.tool_name,
            passed=True,
            message=(
                f"read_scaffold_artifact: {target_path} sha256-matched ({len(content)} bytes); "
                f"bad path + bogus project_id both rejected"
            ),
            duration_ms=(time.time() - start_time) * 1000,
        )
