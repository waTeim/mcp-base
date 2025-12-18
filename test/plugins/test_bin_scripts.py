"""
Test plugin for bin scripts generation and Python-only constraint.

Updated to work with artifact-based scaffold output.
"""
from plugins import TestPlugin, TestResult
import time
import json


class TestBinScripts(TestPlugin):
    """Tests that bin scripts are generated correctly with Python-only constraint."""

    tool_name = "generate_server_scaffold"
    description = "Verifies bin scripts are Python-only (no shell scripts)"
    depends_on = []
    run_after = ["TestGenerateServerScaffold"]

    # Required bin scripts - these must all be generated
    REQUIRED_BIN_SCRIPTS = [
        "bin/add-user.py",
        "bin/create-secrets.py",
        "bin/make-config.py",
        "bin/setup-auth0.py",
        "bin/setup-rbac.py",
    ]

    # Forbidden patterns - actual bin files with these extensions (not docs mentioning them)
    FORBIDDEN_PATTERNS_IN_CONTENT = [
        "#!/bin/bash",             # Bash shebang not allowed in bin scripts
        "#!/bin/sh",               # Sh shebang not allowed in bin scripts
    ]

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            # Generate scaffold with bin scripts enabled (summary mode to get project_id)
            result = await session.call_tool("generate_server_scaffold", arguments={
                "server_name": "Bin Test Server",
                "output_description": "summary",  # Get summary to extract project_id
                "port": 8080,
                "default_namespace": "default",
                "include_helm": False,  # Skip helm to focus on bin
                "include_test": False,  # Skip test to focus on bin
                "include_bin": True     # Must include bin
            })

            # Extract text content from response
            if hasattr(result, 'content') and result.content:
                text_content = result.content[0].text if result.content else ""
            else:
                text_content = str(result)

            # Check for error message
            if text_content.startswith("Error"):
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Scaffold generation failed",
                    error=text_content,
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Extract project_id from the summary output
            # Format: **Project ID**: `bin-test-server-abc12345`
            project_id = None
            for line in text_content.split('\n'):
                if 'Project ID' in line and '`' in line:
                    # Extract the ID between backticks
                    parts = line.split('`')
                    if len(parts) >= 2:
                        project_id = parts[1]
                        break

            if not project_id:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message="Could not extract project_id from scaffold output",
                    error=f"Output: {text_content[:500]}...",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # 1. Verify all required bin scripts are listed
            missing_scripts = []
            for script in self.REQUIRED_BIN_SCRIPTS:
                if script not in text_content:
                    missing_scripts.append(script)

            if missing_scripts:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Missing required bin scripts: {missing_scripts}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # 2. Fetch and verify each bin script content using get_artifact
            python_shebang_count = 0
            forbidden_found = []
            markers_found = 0

            expected_markers = {
                "bin/add-user.py": ["Auth0", "user"],
                "bin/create-secrets.py": ["Kubernetes", "Secret"],
                "bin/make-config.py": ["config", "auth0-config"],
                "bin/setup-auth0.py": ["Auth0", "tenant"],
                "bin/setup-rbac.py": ["RBAC", "ServiceAccount"],
            }

            for script_path in self.REQUIRED_BIN_SCRIPTS:
                # Fetch the artifact content
                artifact_result = await session.call_tool("get_artifact", arguments={
                    "project_id": project_id,
                    "path": script_path
                })

                if hasattr(artifact_result, 'content') and artifact_result.content:
                    script_content = artifact_result.content[0].text if artifact_result.content else ""
                else:
                    script_content = str(artifact_result)

                # Check for error
                if script_content.startswith("Error"):
                    return TestResult(
                        plugin_name=self.get_name(),
                        tool_name=self.tool_name,
                        passed=False,
                        message=f"Failed to fetch artifact: {script_path}",
                        error=script_content,
                        duration_ms=(time.time() - start_time) * 1000
                    )

                # Check for Python shebang
                if "#!/usr/bin/env python3" in script_content:
                    python_shebang_count += 1

                # Check for forbidden shell patterns
                for pattern in self.FORBIDDEN_PATTERNS_IN_CONTENT:
                    if pattern in script_content:
                        forbidden_found.append(f"{script_path}: {pattern}")

                # Check for expected markers (use full path as key)
                if script_path in expected_markers:
                    for marker in expected_markers[script_path]:
                        if marker in script_content:
                            markers_found += 1
                            break

            # Verify no forbidden patterns
            if forbidden_found:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Found forbidden shell script patterns: {forbidden_found}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify Python shebangs (at least 4 out of 5 should have them)
            if python_shebang_count < 4:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Expected Python shebangs for bin scripts, found only {python_shebang_count}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # Verify content markers (at least 3 scripts should have their markers)
            if markers_found < 3:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Bin scripts missing expected content markers (found {markers_found}/5)",
                    duration_ms=(time.time() - start_time) * 1000
                )

            return TestResult(
                plugin_name=self.get_name(),
                tool_name=self.tool_name,
                passed=True,
                message=f"All {len(self.REQUIRED_BIN_SCRIPTS)} bin scripts generated correctly (Python only, {python_shebang_count} with shebangs)",
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
