"""
Artifact Store for Generated Files

Provides in-memory storage for generated artifacts (like scaffold files) that can be
served as MCP resources. This allows tools to return resource_link references instead
of embedding large content directly in tool results, reducing context usage.

Usage:
    # Store an artifact
    artifact_store.store("my-project", "src/main.py", "print('hello')")

    # Get an artifact
    content = artifact_store.get("my-project", "src/main.py")

    # List artifacts in a project
    files = artifact_store.list_project("my-project")

    # Clear a project's artifacts
    artifact_store.clear_project("my-project")
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import threading


@dataclass
class Artifact:
    """Represents a stored artifact."""
    content: str
    mime_type: str
    created_at: datetime
    description: Optional[str] = None


class ArtifactStore:
    """
    Thread-safe in-memory store for generated artifacts.

    Artifacts are organized by project_id and path:
        artifact://{project_id}/{path}
    """

    def __init__(self):
        self._store: Dict[str, Dict[str, Artifact]] = {}
        self._lock = threading.Lock()

    def store(
        self,
        project_id: str,
        path: str,
        content: str,
        mime_type: str = "text/plain",
        description: Optional[str] = None
    ) -> str:
        """
        Store an artifact and return its URI.

        Args:
            project_id: Unique project identifier
            path: File path within project (e.g., "src/main.py")
            content: File content
            mime_type: MIME type (default: text/plain)
            description: Optional description

        Returns:
            Artifact URI (artifact://{project_id}/{path})
        """
        with self._lock:
            if project_id not in self._store:
                self._store[project_id] = {}

            self._store[project_id][path] = Artifact(
                content=content,
                mime_type=mime_type,
                created_at=datetime.now(timezone.utc),
                description=description
            )

        return f"artifact://{project_id}/{path}"

    def get(self, project_id: str, path: str) -> Optional[Artifact]:
        """
        Get an artifact by project and path.

        Args:
            project_id: Project identifier
            path: File path within project

        Returns:
            Artifact or None if not found
        """
        with self._lock:
            project = self._store.get(project_id, {})
            return project.get(path)

    def get_by_uri(self, uri: str) -> Optional[Artifact]:
        """
        Get an artifact by its full URI.

        Args:
            uri: Full artifact URI (artifact://{project_id}/{path})

        Returns:
            Artifact or None if not found
        """
        parsed = self.parse_uri(uri)
        if parsed is None:
            return None
        project_id, path = parsed
        return self.get(project_id, path)

    @staticmethod
    def parse_uri(uri: str) -> Optional[Tuple[str, str]]:
        """
        Parse an artifact URI into (project_id, path).

        Args:
            uri: Artifact URI (artifact://{project_id}/{path})

        Returns:
            (project_id, path) tuple or None if invalid
        """
        if not uri.startswith("artifact://"):
            return None

        remainder = uri[len("artifact://"):]
        if "/" not in remainder:
            return None

        project_id, path = remainder.split("/", 1)
        return (project_id, path)

    def list_project(self, project_id: str) -> List[Tuple[str, str]]:
        """
        List all artifacts in a project.

        Args:
            project_id: Project identifier

        Returns:
            List of (path, uri) tuples
        """
        with self._lock:
            project = self._store.get(project_id, {})
            return [
                (path, f"artifact://{project_id}/{path}")
                for path in sorted(project.keys())
            ]

    def list_all_projects(self) -> List[str]:
        """
        List all project IDs with stored artifacts.

        Returns:
            List of project IDs
        """
        with self._lock:
            return list(self._store.keys())

    def clear_project(self, project_id: str) -> int:
        """
        Clear all artifacts for a project.

        Args:
            project_id: Project identifier

        Returns:
            Number of artifacts cleared
        """
        with self._lock:
            if project_id in self._store:
                count = len(self._store[project_id])
                del self._store[project_id]
                return count
            return 0

    def clear_all(self) -> int:
        """
        Clear all artifacts.

        Returns:
            Total number of artifacts cleared
        """
        with self._lock:
            count = sum(len(p) for p in self._store.values())
            self._store.clear()
            return count

    def get_stats(self) -> Dict[str, int]:
        """
        Get storage statistics.

        Returns:
            Dict with project_count and total_artifacts
        """
        with self._lock:
            return {
                "project_count": len(self._store),
                "total_artifacts": sum(len(p) for p in self._store.values())
            }


# Global singleton instance
artifact_store = ArtifactStore()


def get_mime_type_for_path(path: str) -> str:
    """
    Determine MIME type based on file extension.

    Args:
        path: File path

    Returns:
        MIME type string
    """
    ext_map = {
        ".py": "text/x-python",
        ".yaml": "text/x-yaml",
        ".yml": "text/x-yaml",
        ".json": "application/json",
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".sh": "text/x-shellscript",
        ".bash": "text/x-shellscript",
        ".j2": "text/x-jinja2",
        ".jinja2": "text/x-jinja2",
        ".html": "text/html",
        ".css": "text/css",
        ".js": "text/javascript",
        ".ts": "text/typescript",
        ".toml": "text/x-toml",
        ".gitignore": "text/plain",
        ".helmignore": "text/plain",
        ".dockerignore": "text/plain",
        "Dockerfile": "text/x-dockerfile",
        "Makefile": "text/x-makefile",
    }

    # Check for exact filename matches first
    filename = path.split("/")[-1]
    if filename in ext_map:
        return ext_map[filename]

    # Check by extension
    for ext, mime in ext_map.items():
        if ext.startswith(".") and path.endswith(ext):
            return mime

    return "text/plain"
