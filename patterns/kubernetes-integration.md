# Kubernetes Integration Pattern

This document describes patterns for integrating MCP servers with Kubernetes APIs.

## Overview

MCP servers interact with Kubernetes to manage Custom Resources (CRDs) and core resources. Key patterns:

1. **Lazy client initialization** - Initialize on first use
2. **Async wrappers** - Non-blocking API calls
3. **RBAC configuration** - Proper permissions
4. **Error handling** - Kubernetes-specific errors

## Client Initialization Pattern

```python
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Global clients (lazy initialized)
_custom_api = None
_core_api = None

def _init_kubernetes():
    """Initialize Kubernetes configuration."""
    global _custom_api, _core_api

    if _custom_api is not None:
        return

    try:
        # Try in-cluster config first (when running in K8s)
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except config.ConfigException:
        # Fall back to kubeconfig (local development)
        config.load_kube_config()
        logger.info("Loaded kubeconfig from file")

    _custom_api = client.CustomObjectsApi()
    _core_api = client.CoreV1Api()

def get_custom_api() -> client.CustomObjectsApi:
    """Get CustomObjectsApi for CRD operations."""
    _init_kubernetes()
    return _custom_api

def get_core_api() -> client.CoreV1Api:
    """Get CoreV1Api for core resource operations."""
    _init_kubernetes()
    return _core_api
```

## Async Wrapper Pattern

Kubernetes Python client is synchronous. Wrap calls with `asyncio.to_thread`:

```python
import asyncio

async def list_custom_resources(
    group: str,
    version: str,
    plural: str,
    namespace: str = None
) -> list:
    """List custom resources asynchronously."""
    api = get_custom_api()

    if namespace:
        result = await asyncio.to_thread(
            api.list_namespaced_custom_object,
            group=group,
            version=version,
            namespace=namespace,
            plural=plural
        )
    else:
        result = await asyncio.to_thread(
            api.list_cluster_custom_object,
            group=group,
            version=version,
            plural=plural
        )

    return result.get('items', [])

async def get_custom_resource(
    group: str,
    version: str,
    plural: str,
    name: str,
    namespace: str
) -> dict:
    """Get a specific custom resource."""
    api = get_custom_api()
    return await asyncio.to_thread(
        api.get_namespaced_custom_object,
        group=group,
        version=version,
        namespace=namespace,
        plural=plural,
        name=name
    )

async def create_custom_resource(
    group: str,
    version: str,
    plural: str,
    namespace: str,
    body: dict
) -> dict:
    """Create a custom resource."""
    api = get_custom_api()
    return await asyncio.to_thread(
        api.create_namespaced_custom_object,
        group=group,
        version=version,
        namespace=namespace,
        plural=plural,
        body=body
    )

async def patch_custom_resource(
    group: str,
    version: str,
    plural: str,
    name: str,
    namespace: str,
    body: dict
) -> dict:
    """Patch a custom resource."""
    api = get_custom_api()
    return await asyncio.to_thread(
        api.patch_namespaced_custom_object,
        group=group,
        version=version,
        namespace=namespace,
        plural=plural,
        name=name,
        body=body
    )

async def delete_custom_resource(
    group: str,
    version: str,
    plural: str,
    name: str,
    namespace: str
) -> dict:
    """Delete a custom resource."""
    api = get_custom_api()
    return await asyncio.to_thread(
        api.delete_namespaced_custom_object,
        group=group,
        version=version,
        namespace=namespace,
        plural=plural,
        name=name
    )
```

## Secret Management Pattern

```python
import base64
import secrets
import string

async def create_secret(
    name: str,
    namespace: str,
    data: dict,
    labels: dict = None
) -> dict:
    """Create a Kubernetes secret."""
    api = get_core_api()

    # Encode data values as base64
    encoded_data = {
        k: base64.b64encode(v.encode()).decode()
        for k, v in data.items()
    }

    secret = client.V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels or {}
        ),
        type="Opaque",
        data=encoded_data
    )

    return await asyncio.to_thread(
        api.create_namespaced_secret,
        namespace=namespace,
        body=secret
    )

async def get_secret(name: str, namespace: str) -> dict:
    """Get a secret and decode its data."""
    api = get_core_api()

    secret = await asyncio.to_thread(
        api.read_namespaced_secret,
        name=name,
        namespace=namespace
    )

    # Decode base64 values
    decoded_data = {}
    if secret.data:
        for k, v in secret.data.items():
            decoded_data[k] = base64.b64decode(v).decode()

    return decoded_data

def generate_password(length: int = 32) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
```

## Error Handling Pattern

```python
from kubernetes.client.rest import ApiException

async def safe_get_resource(name: str, namespace: str) -> tuple[dict, str]:
    """
    Safely get a resource with proper error handling.

    Returns:
        Tuple of (resource_dict, error_message)
        If successful: (resource, None)
        If failed: (None, error_message)
    """
    try:
        resource = await get_custom_resource(
            group="example.com",
            version="v1",
            plural="resources",
            name=name,
            namespace=namespace
        )
        return resource, None

    except ApiException as e:
        if e.status == 404:
            return None, f"Resource '{name}' not found in namespace '{namespace}'"
        elif e.status == 403:
            return None, f"Permission denied to access '{name}' in '{namespace}'"
        else:
            return None, f"Kubernetes API error: {e.reason}"

    except Exception as e:
        return None, f"Unexpected error: {str(e)}"
```

## Namespace Resolution Pattern

```python
import os

DEFAULT_NAMESPACE = "default"

def resolve_namespace(namespace: str = None) -> str:
    """
    Resolve the namespace to use for operations.

    Priority:
    1. Explicitly provided namespace
    2. NAMESPACE environment variable
    3. In-cluster namespace file
    4. Default namespace
    """
    if namespace:
        return namespace

    # Check environment variable
    env_ns = os.environ.get("NAMESPACE")
    if env_ns:
        return env_ns

    # Check in-cluster namespace file
    ns_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    try:
        with open(ns_file, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        pass

    return DEFAULT_NAMESPACE
```

## RBAC Configuration

### ClusterRole for CRD Access

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: mcp-server-role
rules:
  # Custom Resource access
  - apiGroups: ["example.com"]
    resources: ["resources", "resources/status"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

  # Secret management
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "create", "update", "patch", "delete"]

  # Read-only access for related resources
  - apiGroups: [""]
    resources: ["pods", "pods/log", "events", "services"]
    verbs: ["get", "list", "watch"]
```

### ClusterRoleBinding

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: mcp-server-binding
subjects:
  - kind: ServiceAccount
    name: mcp-server
    namespace: mcp
roleRef:
  kind: ClusterRole
  name: mcp-server-role
  apiGroup: rbac.authorization.k8s.io
```

## Watch Pattern (for Real-time Updates)

```python
from kubernetes import watch

async def watch_resources(
    group: str,
    version: str,
    plural: str,
    namespace: str,
    callback
):
    """Watch for resource changes."""
    api = get_custom_api()
    w = watch.Watch()

    def sync_watch():
        for event in w.stream(
            api.list_namespaced_custom_object,
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            timeout_seconds=300
        ):
            callback(event['type'], event['object'])

    await asyncio.to_thread(sync_watch)
```

## Best Practices

1. **Lazy initialize clients** - Don't connect until needed
2. **Use asyncio.to_thread** - Keep event loop responsive
3. **Handle API errors gracefully** - Provide actionable messages
4. **Use least privilege RBAC** - Only request needed permissions
5. **Namespace isolation** - Default to user's namespace
6. **Secret encryption** - Use Kubernetes secrets for sensitive data
7. **Connection pooling** - Reuse client instances
