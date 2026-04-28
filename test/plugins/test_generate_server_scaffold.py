"""
Test plugin for generate_server_scaffold tool.

Validates the resource-first manifest contract: the tool returns compact
coordination metadata (project_id, artifacts, retrieval_contract, workflow);
bulk file bytes are NOT in the tool output and must be fetched via
resources/read against the scaffold:// URIs.

Also publishes project_id and the artifact list into ctx.shared so
downstream plugins (list_artifacts, read_scaffold_artifact, ...) can reuse
this scaffold instead of generating their own.
"""
from plugins import TestPlugin, TestResult, TestContext
from typing import Optional
import time
import json


class TestGenerateServerScaffold(TestPlugin):
    """Tests the generate_server_scaffold tool."""

    tool_name = "generate_server_scaffold"
    description = "Verifies scaffold generation produces complete project"
    depends_on = []
    run_after = ["TestRenderTemplate"]

    async def test(self, session, ctx: Optional[TestContext] = None) -> TestResult:
        start_time = time.time()

        try:
            result = await session.call_tool("generate_server_scaffold", arguments={
                "server_name": "My Test Server"
            })

            if hasattr(result, 'content') and result.content:
                text_content = result.content[0].text if result.content else ""
            else:
                text_content = str(result)

            try:
                data = json.loads(text_content)
            except json.JSONDecodeError:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Response is not valid JSON",
                    error=f"Got: {text_content[:200]}...",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Resource-first manifest shape
            required_fields = [
                "project_id", "server_name", "file_count",
                "artifacts", "retrieval_contract", "workflow",
            ]
            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing required fields: {missing_fields}",
                    error=f"Top-level keys: {sorted(data.keys())}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            artifacts = data.get("artifacts", [])
            if not isinstance(artifacts, list) or not artifacts:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="`artifacts` is missing, empty, or not a list",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # file_count must agree with artifacts length
            if data.get("file_count") != len(artifacts):
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=(
                        f"file_count ({data.get('file_count')}) "
                        f"doesn't match artifacts length ({len(artifacts)})"
                    ),
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Each artifact carries the materialization contract fields
            artifact_required = {"path", "uri", "sha256", "size_bytes"}
            for i, a in enumerate(artifacts):
                missing = artifact_required - set(a)
                if missing:
                    return TestResult(
                        plugin_name=self.get_name(),
                        tool_name=self.tool_name,
                        passed=False,
                        message=f"artifact[{i}] missing fields: {sorted(missing)}",
                        error=f"Got: {sorted(a.keys())}",
                        duration_ms=(time.time() - start_time) * 1000
                    )
                if not a["uri"].startswith(f"scaffold://{data['project_id']}/"):
                    return TestResult(
                        plugin_name=self.get_name(),
                        tool_name=self.tool_name,
                        passed=False,
                        message=f"artifact[{i}].uri does not match scaffold://<project_id>/ prefix",
                        error=f"Got: {a['uri']}",
                        duration_ms=(time.time() - start_time) * 1000
                    )

            paths = {a["path"] for a in artifacts}
            expected_files = [
                "src/my_test_server_server.py",
                "src/my_test_server_test_server.py",
                "src/my_test_server_tools.py",
                "src/prompt_registry.py",
                "Dockerfile",
                "test/Dockerfile",
                "requirements.txt",
                "Makefile",
                "chart/Chart.yaml",
                "chart/values.yaml",
                "chart/templates/deployment.yaml",
                "chart/templates/prompts-configmap.yaml",
                "test/test-mcp.py",
                "test/plugins/__init__.py",
            ]
            missing_files = [f for f in expected_files if f not in paths]
            if missing_files:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing expected files: {missing_files}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Retrieval contract should describe the resource-first pathway
            contract = data.get("retrieval_contract", {})
            for key in ("bulk_bytes", "metadata", "gate"):
                if key not in contract:
                    return TestResult(
                        plugin_name=self.get_name(),
                        tool_name=self.tool_name,
                        passed=False,
                        message=f"retrieval_contract missing '{key}'",
                        error=f"Got: {sorted(contract.keys())}",
                        duration_ms=(time.time() - start_time) * 1000
                    )

            workflow = data.get("workflow", [])
            if not isinstance(workflow, list) or not workflow:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="workflow should be a non-empty list",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Publish project_id + artifact paths so downstream plugins
            # (list_artifacts, read_scaffold_artifact, ...) can reuse this
            # scaffold instead of generating their own.
            if ctx is not None:
                ctx.shared["scaffold_project_id"] = data["project_id"]
                ctx.shared["scaffold_artifacts"] = artifacts

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=(
                    f"Scaffold manifest valid: {len(artifacts)} artifacts, "
                    f"project_id={data['project_id']}"
                ),
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
