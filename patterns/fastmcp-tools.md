# FastMCP Tool Implementation Pattern

This document describes the pattern for implementing MCP tools using FastMCP with user context extraction.

## Overview

MCP tools in this architecture follow a specific pattern:
1. **FastMCP decorator** - `@mcp.tool()` for automatic schema generation
2. **Context wrapper** - `@with_mcp_context` for user identification
3. **Async implementation** - All tools are async for non-blocking I/O
4. **LLM-optimized responses** - Formatted for AI consumption

## Tool Registration Pattern

```python
from fastmcp import FastMCP, Context
from mcp_context import MCPContext, with_mcp_context

mcp = FastMCP("server-name")

@with_mcp_context
async def my_tool_impl(
    ctx: MCPContext,
    required_param: str,
    optional_param: str = None,
    detail_level: Literal["concise", "detailed"] = "concise"
) -> str:
    """
    Brief description of what this tool does.

    Detailed explanation for LLM consumption explaining when and why
    to use this tool.

    Args:
        required_param: Description with examples
        optional_param: Optional parameter description
        detail_level: Amount of detail in response

    Returns:
        Formatted string describing the result

    Examples:
        - Basic usage: my_tool(required_param="value")
        - With options: my_tool(required_param="value", detail_level="detailed")

    Error Handling:
        - 404: Resource not found
        - 403: Permission denied
    """
    # Log user context for audit
    user = ctx.preferred_username or ctx.user_id or "anonymous"
    await ctx.info(f"User {user} calling my_tool with {required_param}")

    try:
    # Implementation
    result = await do_something(required_param, optional_param)
    return format_response(result, detail_level)

@mcp.tool(name="my_tool")
async def my_tool(
    required_param: str,
    optional_param: str = None,
    detail_level: Literal["concise", "detailed"] = "concise",
    ctx: Context = None
) -> str:
    """Thin tool wrapper that passes FastMCP Context through."""
    return await my_tool_impl(
        ctx=ctx,
        required_param=required_param,
        optional_param=optional_param,
        detail_level=detail_level
    )
    except Exception as e:
        return format_error_message(e, "calling my_tool")
```

## MCPContext Pattern

The `MCPContext` class wraps FastMCP's `Context` to extract user information from JWT tokens:

```python
class MCPContext:
    """Extended MCP Context with user identification."""

    def __init__(self, ctx: FastMCPContext):
        self.ctx = ctx
        self.user_id: Optional[str] = None
        self.preferred_username: Optional[str] = None
        self.issuer: Optional[str] = None
        self._extract_user_info()

    def _extract_user_info(self) -> None:
        """Extract user info from HTTP request JWT."""
        try:
            request = get_http_request()
            user_info = extract_user_info_from_request(request)
            if user_info:
                self.user_id = user_info['user_id']
                self.preferred_username = user_info['preferred_username']
                self.issuer = user_info['issuer']
        except Exception:
            pass  # Non-HTTP transport

    def __getattr__(self, name: str) -> Any:
        """Delegate to underlying FastMCP Context."""
        return getattr(self.ctx, name)
```

## with_mcp_context Decorator Pattern

This decorator intercepts FastMCP's Context injection and wraps it. Use it on
implementation functions, then have the `@mcp.tool` wrapper pass the FastMCP
`Context` through as a named argument (`ctx` or `context`).

```python
def with_mcp_context(func):
    """Wrap FastMCP Context into MCPContext with user info."""
    import functools
    import inspect

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Find FastMCPContext in args or kwargs
        fastmcp_ctx = None

        if args and isinstance(args[0], FastMCPContext):
            fastmcp_ctx = args[0]
            args = args[1:]

        if not fastmcp_ctx:
            for key in ['ctx', 'context']:
                if key in kwargs and isinstance(kwargs[key], FastMCPContext):
                    fastmcp_ctx = kwargs.pop(key)
                    break

        # Create MCPContext and call function
        if fastmcp_ctx:
            mcp_ctx = MCPContext(fastmcp_ctx)
            return await func(mcp_ctx, *args, **kwargs)
        else:
            return await func(*args, **kwargs)

    return wrapper
```

## Response Formatting Patterns

### Character Limit

```python
CHARACTER_LIMIT = 25000

def truncate_response(response: str, limit: int = CHARACTER_LIMIT) -> str:
    """Truncate response to fit within character limit."""
    if len(response) <= limit:
        return response
    msg = f"\n\n... [Truncated. Showing {limit} of {len(response)} chars]"
    return response[:limit - len(msg)] + msg
```

### Error Messages

```python
def format_error_message(error: Exception, context: str = "") -> str:
    """Format error with actionable suggestions."""
    result = f"## Error: {context}\n\n"
    result += f"**Type:** {type(error).__name__}\n"
    result += f"**Message:** {str(error)}\n"

    # Add suggestions based on HTTP status code
    status = getattr(error, 'status', None)
    if status == 404:
        result += "\n### Suggestions:\n"
        result += "- Resource not found\n"
        result += "- Verify name and namespace\n"
    elif status == 403:
        result += "\n### Suggestions:\n"
        result += "- Check RBAC permissions\n"

    return result
```

## Input Validation with Pydantic

Use Pydantic models for complex input validation:

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class CreateResourceInput(BaseModel):
    """Input for create_resource tool."""
    name: str = Field(
        ...,
        description="Name of the resource",
        pattern=r'^[a-z][a-z0-9-]*[a-z0-9]$'
    )
    namespace: Optional[str] = Field(
        None,
        description="Kubernetes namespace"
    )
    replicas: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of replicas (1-10)"
    )
```

## Kubernetes Integration Pattern

```python
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Lazy initialization
_custom_api = None

def get_custom_api():
    global _custom_api
    if _custom_api is None:
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        _custom_api = client.CustomObjectsApi()
    return _custom_api

# Async wrapper for blocking calls
async def get_resource(name: str, namespace: str) -> dict:
    api = get_custom_api()
    return await asyncio.to_thread(
        api.get_namespaced_custom_object,
        group="example.com",
        version="v1",
        namespace=namespace,
        plural="resources",
        name=name
    )
```

## Best Practices

1. **Always use `@with_mcp_context`** on tool implementations
2. **Log user context** at the start of each tool for audit trails
3. **Use async/await** for all I/O operations
4. **Truncate responses** to prevent context overflow
5. **Provide actionable error messages** with suggestions
6. **Use comprehensive docstrings** - FastMCP generates schemas from them
7. **Include examples** in docstrings for LLM understanding
