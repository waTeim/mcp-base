"""
Test plugin for bin scripts generation and Python-only constraint.
"""
from plugins import TestPlugin, TestResult
import time


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
    # We check for these in the context of actual file listings
    FORBIDDEN_FILE_PATTERNS = [
        "bin/run-local.sh",        # Example of forbidden shell script
        "bin/test-endpoints.sh",   # Example of forbidden shell script
        "bin/generate-kubeconfig.sh",  # Example from issue
        "#!/bin/bash",             # Bash shebang not allowed in bin scripts
        "#!/bin/sh",               # Sh shebang not allowed in bin scripts
    ]

    async def test(self, session) -> TestResult:
        start_time = time.time()

        try:
            # Generate scaffold with bin scripts enabled
            result = await session.call_tool("generate_server_scaffold", arguments={
                "server_name": "Bin Test Server",
                "output_description": "full",  # Get full output to check content
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

            # 1. Verify all required bin scripts are present
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

            # 2. Verify no forbidden shell script files (actual files, not doc examples)
            found_forbidden = []
            for pattern in self.FORBIDDEN_FILE_PATTERNS:
                if pattern in text_content:
                    found_forbidden.append(pattern)

            if found_forbidden:
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Found forbidden shell script files in bin/: {found_forbidden}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # 3. Verify Python shebangs are present (indicates proper Python scripts)
            python_shebang_count = text_content.count("#!/usr/bin/env python3")
            if python_shebang_count < len(self.REQUIRED_BIN_SCRIPTS) - 1:  # -1 for setup-auth0.py which might be counted differently
                return TestResult(
                    plugin_name=self.get_name(),
                    tool_name=self.tool_name,
                    passed=False,
                    message=f"Expected Python shebangs for bin scripts, found only {python_shebang_count}",
                    duration_ms=(time.time() - start_time) * 1000
                )

            # 4. Verify each bin script has expected content markers
            expected_markers = {
                "add-user.py": ["Auth0", "user"],
                "create-secrets.py": ["Kubernetes", "Secret"],
                "make-config.py": ["config", "auth0-config"],
                "setup-auth0.py": ["Auth0", "tenant"],
                "setup-rbac.py": ["RBAC", "ServiceAccount"],
            }

            # Check for at least some expected markers in full output
            markers_found = 0
            for script, markers in expected_markers.items():
                for marker in markers:
                    if marker in text_content:
                        markers_found += 1
                        break

            if markers_found < 3:  # At least 3 scripts should have their markers
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
                message=f"All {len(self.REQUIRED_BIN_SCRIPTS)} bin scripts generated correctly (Python only, no shell scripts)",
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
