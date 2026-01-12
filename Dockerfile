# MCP Base Server - Production Dockerfile
# Builds a container for the MCP server construction assistant

FROM python:3.11-slim

# Metadata
LABEL maintainer="MCP Base"
LABEL description="MCP Server for constructing other MCP servers"
LABEL version="0.1.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/mcp_base_server.py .
COPY src/mcp_base_test_server.py .
COPY src/mcp_base_tools.py .
COPY src/artifact_store.py .
COPY src/user_hash.py .
COPY src/auth_oidc.py .
COPY src/auth_fastmcp.py .
COPY src/mcp_context.py .

# Copy templates and patterns
COPY templates/ ./templates/
COPY patterns/ ./patterns/

# Create a non-root user for security
RUN useradd -m -u 1000 mcpuser && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

# Expose HTTP port
EXPOSE 4208

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:4208/healthz || exit 1

# Default to HTTP transport (for Kubernetes deployment)
# OIDC configuration should be provided via config file at /etc/mcp/oidc.yaml
CMD ["python", "mcp_base_server.py", "--host", "0.0.0.0", "--port", "4208"]
