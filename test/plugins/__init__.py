"""
MCP Base Test Plugin System

Plugins are Python modules that test individual MCP tools.
Each plugin should inherit from TestPlugin and implement the test() method.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TestResult:
    """Result of a test plugin execution."""
    plugin_name: str
    tool_name: str
    passed: bool
    message: str
    error: Optional[str] = None
    duration_ms: Optional[float] = None


@dataclass
class TestContext:
    """
    Per-run context passed to plugins that opt-in.

    Plugins receive this only if their `test()` signature declares a `ctx`
    parameter — older single-arg plugins keep working unchanged.

    Attributes:
        base_url: The MCP endpoint URL the runner connected to
            (e.g. "http://127.0.0.1:38621/test"). Strip the path suffix
            for non-MCP endpoints like /healthz.
        shared: Mutable dict for plugins to publish data for downstream
            plugins (e.g. a scaffold project_id). Use `run_after` /
            `depends_on` to enforce ordering.
    """
    base_url: str
    shared: Dict[str, Any] = field(default_factory=dict)


class TestPlugin:
    """Base class for MCP test plugins."""

    # Override these in your plugin
    tool_name: str = "unknown"
    description: str = "No description"
    depends_on: list = []  # Hard dependencies - test skipped if these fail
    run_after: list = []   # Soft dependencies - test runs after these, but not skipped if they fail

    async def test(self, session, ctx: Optional[TestContext] = None) -> TestResult:
        """
        Run the test for this tool.

        Args:
            session: MCP ClientSession instance
            ctx: Optional per-run context (base_url, shared scratch dict).
                Older plugins may declare `(self, session)` only and the
                runner will call them without ctx.

        Returns:
            TestResult with pass/fail status and details
        """
        raise NotImplementedError("Plugin must implement test() method")

    def get_name(self) -> str:
        """Get the plugin name (defaults to class name)."""
        return self.__class__.__name__
