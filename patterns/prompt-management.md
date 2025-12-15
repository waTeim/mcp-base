# Prompt Management Pattern

This document describes how to manage MCP prompts in a production Kubernetes environment with versioning, validation, and hot-reloading.

## Overview

MCP servers can expose prompts that guide AI clients. In production, prompts need to be:

1. **Versioned** - Track changes with semver and hashes
2. **Validated** - Ensure prompts meet schema requirements
3. **Reloadable** - Update prompts without restarting the server
4. **Deployment-friendly** - Store in ConfigMaps for Kubernetes

## Prompt Bundle Structure

### Manifest Format

```yaml
# prompts.yaml
version: "1.0.0"
updated_at: "2024-01-15T10:30:00Z"
prompts:
  - id: "kubernetes-troubleshoot"
    name: "Kubernetes Troubleshooting"
    description: "Guide for diagnosing Kubernetes issues"
    template: |
      Analyze the following Kubernetes issue:

      Namespace: {{ namespace }}
      Resource: {{ resource_type }}/{{ resource_name }}
      Symptoms: {{ symptoms }}

      Provide:
      1. Likely root causes
      2. Diagnostic commands to run
      3. Remediation steps
    arguments:
      - name: namespace
        description: "Kubernetes namespace"
        required: true
      - name: resource_type
        description: "Resource type (pod, deployment, service, etc.)"
        required: true
      - name: resource_name
        description: "Name of the resource"
        required: true
      - name: symptoms
        description: "Observed symptoms or error messages"
        required: true

  - id: "deployment-review"
    name: "Deployment Review"
    description: "Review a deployment configuration"
    template: |
      Review this Kubernetes deployment for best practices:

      {{ deployment_yaml }}

      Check for:
      - Resource limits and requests
      - Health checks (liveness, readiness)
      - Security context
      - Pod disruption budget considerations
    arguments:
      - name: deployment_yaml
        description: "The deployment YAML to review"
        required: true
```

### Bundle Metadata

The server automatically computes:

```python
{
    "version": "1.0.0",
    "bundle_hash": "sha256:abc123...",  # Hash of entire bundle
    "updated_at": "2024-01-15T10:30:00Z",
    "prompt_count": 2
}
```

## Prompt Registry Implementation

### Core Registry

```python
# prompt_registry.py
import hashlib
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, validator
import logging

logger = logging.getLogger(__name__)


class PromptArgument(BaseModel):
    """Schema for prompt arguments."""
    name: str
    description: str
    required: bool = True


class PromptDefinition(BaseModel):
    """Schema for a single prompt definition."""
    id: str
    name: str
    description: str
    template: str
    arguments: List[PromptArgument] = []

    @validator('template')
    def validate_template_size(cls, v):
        max_size = 10000  # 10KB max template size
        if len(v) > max_size:
            raise ValueError(f"Template exceeds max size of {max_size} bytes")
        return v

    @validator('id')
    def validate_id_format(cls, v):
        import re
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError("ID must be lowercase alphanumeric with dashes")
        return v


class PromptBundle(BaseModel):
    """Schema for the entire prompt bundle."""
    version: str
    updated_at: Optional[str] = None
    prompts: List[PromptDefinition]

    @validator('prompts')
    def validate_prompt_count(cls, v):
        max_prompts = 100
        if len(v) > max_prompts:
            raise ValueError(f"Too many prompts (max {max_prompts})")
        return v


@dataclass
class PromptRegistry:
    """Registry for managing MCP prompts with versioning and hot-reload."""

    prompts_path: Path
    bundle: Optional[PromptBundle] = None
    bundle_hash: str = ""
    loaded_at: Optional[datetime] = None
    _file_mtime: float = 0.0

    def load(self) -> bool:
        """Load prompts from file. Returns True if bundle changed."""
        if not self.prompts_path.exists():
            logger.warning(f"Prompts file not found: {self.prompts_path}")
            return False

        try:
            # Check if file changed
            current_mtime = self.prompts_path.stat().st_mtime
            if current_mtime == self._file_mtime and self.bundle is not None:
                return False  # No change

            # Load and parse
            content = self.prompts_path.read_text()
            if self.prompts_path.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)

            # Validate against schema
            new_bundle = PromptBundle(**data)

            # Compute hash
            new_hash = self._compute_hash(content)

            # Check if content actually changed
            if new_hash == self.bundle_hash:
                self._file_mtime = current_mtime
                return False

            # Update registry
            self.bundle = new_bundle
            self.bundle_hash = new_hash
            self._file_mtime = current_mtime
            self.loaded_at = datetime.now(timezone.utc)

            logger.info(f"Loaded {len(new_bundle.prompts)} prompts, "
                       f"version={new_bundle.version}, hash={new_hash[:16]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to load prompts: {e}")
            return False

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of bundle content."""
        return hashlib.sha256(content.encode()).hexdigest()

    def get_manifest(self) -> Dict[str, Any]:
        """Get bundle manifest for clients."""
        if not self.bundle:
            return {"error": "No prompts loaded"}

        return {
            "version": self.bundle.version,
            "bundle_hash": f"sha256:{self.bundle_hash}",
            "updated_at": self.bundle.updated_at or self.loaded_at.isoformat(),
            "prompt_count": len(self.bundle.prompts),
            "prompt_ids": [p.id for p in self.bundle.prompts]
        }

    def get_prompt(self, prompt_id: str) -> Optional[PromptDefinition]:
        """Get a specific prompt by ID."""
        if not self.bundle:
            return None
        for prompt in self.bundle.prompts:
            if prompt.id == prompt_id:
                return prompt
        return None

    def get_all_prompts(self) -> List[PromptDefinition]:
        """Get all prompts."""
        return self.bundle.prompts if self.bundle else []

    def check_for_updates(self) -> bool:
        """Check if file changed and reload if needed."""
        if not self.prompts_path.exists():
            return False

        current_mtime = self.prompts_path.stat().st_mtime
        if current_mtime != self._file_mtime:
            return self.load()
        return False
```

### Registering with MCP

```python
# In your *_tools.py file

from prompt_registry import PromptRegistry, PromptDefinition
from mcp.types import Prompt, PromptArgument as MCPPromptArgument

# Global registry instance
_prompt_registry: Optional[PromptRegistry] = None


def get_prompt_registry() -> PromptRegistry:
    """Get or create the prompt registry singleton."""
    global _prompt_registry
    if _prompt_registry is None:
        prompts_path = Path(os.environ.get(
            "PROMPTS_PATH",
            "/etc/mcp/prompts.yaml"
        ))
        _prompt_registry = PromptRegistry(prompts_path=prompts_path)
        _prompt_registry.load()
    return _prompt_registry


def register_prompts(mcp):
    """Register prompts from the registry with the MCP server."""
    registry = get_prompt_registry()

    # Register each prompt
    for prompt_def in registry.get_all_prompts():
        @mcp.prompt(name=prompt_def.id)
        async def get_prompt(
            prompt_id: str = prompt_def.id,
            **kwargs
        ) -> str:
            """Dynamic prompt handler."""
            reg = get_prompt_registry()
            prompt = reg.get_prompt(prompt_id)
            if not prompt:
                return f"Error: Prompt '{prompt_id}' not found"

            # Render template with provided arguments
            template = prompt.template
            for key, value in kwargs.items():
                template = template.replace(f"{{{{ {key} }}}}", str(value))

            return template
```

## Kubernetes Deployment

### ConfigMap for Prompts

```yaml
# chart/templates/prompts-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "chart.fullname" . }}-prompts
  labels:
    {{- include "chart.labels" . | nindent 4 }}
data:
  prompts.yaml: |
    version: "1.0.0"
    updated_at: {{ now | date "2006-01-02T15:04:05Z07:00" | quote }}
    prompts:
      {{- toYaml .Values.prompts | nindent 6 }}
```

### Deployment Volume Mount

```yaml
# In deployment.yaml
spec:
  template:
    spec:
      containers:
        - name: {{ .Chart.Name }}
          volumeMounts:
            - name: prompts
              mountPath: /etc/mcp
              readOnly: true
      volumes:
        - name: prompts
          configMap:
            name: {{ include "chart.fullname" . }}-prompts
```

### Values.yaml

```yaml
# chart/values.yaml
prompts:
  - id: "example-prompt"
    name: "Example Prompt"
    description: "An example prompt template"
    template: |
      This is an example prompt.
      Input: {{ input }}
    arguments:
      - name: input
        description: "User input"
        required: true
```

## Admin Endpoints

### Reload Endpoint

```python
from fastapi import HTTPException

@app.post("/admin/reload-prompts")
async def reload_prompts():
    """Admin endpoint to reload prompts from file."""
    registry = get_prompt_registry()
    changed = registry.load()

    if changed:
        return {
            "status": "reloaded",
            "manifest": registry.get_manifest()
        }
    return {
        "status": "unchanged",
        "manifest": registry.get_manifest()
    }


@app.get("/prompts/manifest")
async def get_prompts_manifest():
    """Get the prompt bundle manifest with ETag support."""
    registry = get_prompt_registry()
    manifest = registry.get_manifest()

    # Return with ETag header
    from fastapi.responses import JSONResponse
    response = JSONResponse(content=manifest)
    response.headers["ETag"] = manifest.get("bundle_hash", "")
    return response
```

### Health Check Integration

```python
@app.get("/healthz")
async def health_check():
    """Health check including prompt registry status."""
    registry = get_prompt_registry()
    manifest = registry.get_manifest()

    return {
        "status": "healthy",
        "prompts": {
            "loaded": registry.bundle is not None,
            "version": manifest.get("version"),
            "count": manifest.get("prompt_count", 0)
        }
    }
```

## Client Usage

### Fetching Prompts

```python
# Client-side code
import httpx

async def fetch_prompt_manifest(server_url: str) -> dict:
    """Fetch prompt manifest from server."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{server_url}/prompts/manifest")
        return response.json()


async def fetch_prompt_if_changed(
    server_url: str,
    cached_hash: str
) -> tuple[dict, bool]:
    """Fetch manifest only if changed (using ETag)."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{server_url}/prompts/manifest",
            headers={"If-None-Match": cached_hash}
        )

        if response.status_code == 304:
            return None, False  # Not modified

        return response.json(), True
```

### Using via MCP Protocol

```python
# Using MCP client
async with ClientSession(read, write) as session:
    # List available prompts
    prompts = await session.list_prompts()

    for prompt in prompts.prompts:
        print(f"- {prompt.name}: {prompt.description}")

    # Get a specific prompt with arguments
    result = await session.get_prompt(
        "kubernetes-troubleshoot",
        arguments={
            "namespace": "production",
            "resource_type": "pod",
            "resource_name": "api-server-xyz",
            "symptoms": "CrashLoopBackOff"
        }
    )
```

## Validation and Safety

### Schema Validation

The `PromptBundle` Pydantic model enforces:

1. **ID format**: Lowercase alphanumeric with dashes only
2. **Template size**: Max 10KB per template
3. **Prompt count**: Max 100 prompts per bundle
4. **Required fields**: All required fields validated

### Runtime Guardrails

```python
# In prompt_registry.py

FORBIDDEN_PATTERNS = [
    "ignore previous",
    "disregard all",
    "system prompt",
    "you are now",
]

def validate_prompt_content(template: str) -> bool:
    """Check template doesn't contain prompt injection patterns."""
    lower_template = template.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in lower_template:
            logger.warning(f"Prompt contains forbidden pattern: {pattern}")
            return False
    return True
```

## Best Practices

1. **Version your prompts** - Use semver and update `version` on changes
2. **Keep prompts focused** - One task per prompt, clear arguments
3. **Test prompt changes** - Validate before deploying to production
4. **Monitor usage** - Log which prompt version was used per request
5. **Gradual rollout** - Use feature flags or A/B testing for new prompts
6. **Cache wisely** - Use ETag/If-None-Match to reduce server load
7. **Document prompts** - Clear descriptions help clients pick the right one

## File Watching (Optional)

For development, watch for file changes:

```python
import asyncio
from watchfiles import awatch

async def watch_prompts_file(prompts_path: Path):
    """Watch prompts file for changes and reload."""
    async for changes in awatch(prompts_path):
        logger.info(f"Prompts file changed: {changes}")
        registry = get_prompt_registry()
        registry.load()
```

Add to server startup:
```python
if os.environ.get("WATCH_PROMPTS") == "true":
    asyncio.create_task(watch_prompts_file(Path("/etc/mcp/prompts.yaml")))
```
