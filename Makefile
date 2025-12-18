# Makefile for MCP Base Server
# Builds and pushes container images

# Default target
.PHONY: all
all: config build

# Include auto-generated configuration from make-config.py
-include make.env

# Default values (overridden by make.env)
REGISTRY ?= ghcr.io/your-org
IMAGE_NAME ?= mcp-base-server
IMAGE_NAME_TEST ?= mcp-base-test-server
TAG ?= latest
PLATFORM ?= linux/amd64
CONTAINER_TOOL ?= docker
HELM_RELEASE ?= mcp-base
HELM_NAMESPACE ?= default

# Derived values - construct full image names from REGISTRY and IMAGE_NAME
IMAGE_FULL := $(REGISTRY)/$(IMAGE_NAME):$(TAG)
IMAGE_FULL_TEST := $(REGISTRY)/$(IMAGE_NAME_TEST):$(TAG)

#
# Configuration targets
#

.PHONY: config
config: make.env ## Generate make.env configuration file

make.env:
	@echo "Generating make.env configuration..."
	python3 bin/make-config.py
	@echo "Configuration generated. Edit make.env to customize settings."

.PHONY: config-show
config-show: make.env ## Show current configuration
	@echo "Current Configuration:"
	@echo "  REGISTRY:         $(REGISTRY)"
	@echo "  IMAGE_NAME:       $(IMAGE_NAME)"
	@echo "  IMAGE_NAME_TEST:  $(IMAGE_NAME_TEST)"
	@echo "  TAG:              $(TAG)"
	@echo "  IMAGE_FULL:       $(IMAGE_FULL)"
	@echo "  IMAGE_FULL_TEST:  $(IMAGE_FULL_TEST)"
	@echo "  PLATFORM:         $(PLATFORM)"
	@echo "  CONTAINER_TOOL:   $(CONTAINER_TOOL)"
	@echo "  HELM_RELEASE:     $(HELM_RELEASE)"
	@echo "  HELM_NAMESPACE:   $(HELM_NAMESPACE)"

#
# Container build targets
#

.PHONY: build
build: make.env ## Build container image
	@echo "Building container image: $(IMAGE_FULL)"
	$(CONTAINER_TOOL) build --tag $(IMAGE_FULL) --platform $(PLATFORM) --file Dockerfile .
	@echo "✓ Built: $(IMAGE_FULL)"

.PHONY: build-no-cache
build-no-cache: make.env ## Build container image without cache
	@echo "Building container image (no cache): $(IMAGE_FULL)"
	$(CONTAINER_TOOL) build \
		--no-cache \
		--tag $(IMAGE_FULL) \
		--platform $(PLATFORM) \
		--file Dockerfile \
		.
	@echo "✓ Built: $(IMAGE_FULL)"

.PHONY: push
push: make.env ## Push container image to registry
	@echo "Pushing container image: $(IMAGE_FULL)"
	$(CONTAINER_TOOL) push $(IMAGE_FULL)
	@echo "✓ Pushed: $(IMAGE_FULL)"

.PHONY: build-push
build-push: build push ## Build and push container image

.PHONY: build-test
build-test: make.env ## Build test server container image
	@echo "Building test server image: $(IMAGE_FULL_TEST)"
	$(CONTAINER_TOOL) build --tag $(IMAGE_FULL_TEST) --platform $(PLATFORM) --file Dockerfile.test .
	@echo "✓ Built: $(IMAGE_FULL_TEST)"

.PHONY: build-test-no-cache
build-test-no-cache: make.env ## Build test server image without cache
	@echo "Building test server image (no cache): $(IMAGE_FULL_TEST)"
	$(CONTAINER_TOOL) build \
		--no-cache \
		--tag $(IMAGE_FULL_TEST) \
		--platform $(PLATFORM) \
		--file Dockerfile.test \
		.
	@echo "✓ Built: $(IMAGE_FULL_TEST)"

.PHONY: build-all
build-all: build build-test ## Build both main and test server images

.PHONY: push-test
push-test: make.env ## Push test server image to registry
	@echo "Pushing test server image: $(IMAGE_FULL_TEST)"
	$(CONTAINER_TOOL) push $(IMAGE_FULL_TEST)
	@echo "✓ Pushed: $(IMAGE_FULL_TEST)"

.PHONY: push-all
push-all: build-all push push-test ## Build and push both main and test server images

.PHONY: test-image
test-image: make.env ## Test main server image locally
	@echo "Testing container image: $(IMAGE_FULL)"
	@echo "Starting container in HTTP mode..."
	@echo "Press Ctrl+C to stop"
	$(CONTAINER_TOOL) run --rm -it \
		-p 8000:8000 \
		--name mcp-base-test \
		$(IMAGE_FULL)

.PHONY: test-image-test
test-image-test: make.env ## Test test server image locally
	@echo "Testing test server image: $(IMAGE_FULL_TEST)"
	@echo "Starting test server container..."
	@echo "Press Ctrl+C to stop"
	$(CONTAINER_TOOL) run --rm -it \
		-p 8001:8001 \
		--name mcp-base-test-sidecar \
		$(IMAGE_FULL_TEST)

#
# Helm chart targets
#

.PHONY: helm-lint
helm-lint: ## Lint Helm chart
	@echo "Linting Helm chart..."
	helm lint chart/

.PHONY: helm-template
helm-template: ## Render Helm chart templates
	@echo "Rendering Helm chart templates..."
	helm template $(HELM_RELEASE) chart/ \
		--namespace $(HELM_NAMESPACE) \
		--set image.repository=$(REGISTRY)/$(IMAGE_NAME) \
		--set image.tag=$(TAG)

.PHONY: helm-install
helm-install: make.env ## Install Helm chart
	@echo "Installing Helm chart: $(HELM_RELEASE)"
	helm upgrade --install $(HELM_RELEASE) chart/ \
		--namespace $(HELM_NAMESPACE) \
		--create-namespace \
		--set image.repository=$(REGISTRY)/$(IMAGE_NAME) \
		--set image.tag=$(TAG) \
		--wait
	@echo "✓ Installed: $(HELM_RELEASE) in namespace $(HELM_NAMESPACE)"

.PHONY: helm-upgrade
helm-upgrade: make.env ## Upgrade Helm release
	@echo "Upgrading Helm release: $(HELM_RELEASE)"
	helm upgrade $(HELM_RELEASE) chart/ \
		--namespace $(HELM_NAMESPACE) \
		--set image.repository=$(REGISTRY)/$(IMAGE_NAME) \
		--set image.tag=$(TAG) \
		--wait
	@echo "✓ Upgraded: $(HELM_RELEASE)"

.PHONY: helm-uninstall
helm-uninstall: ## Uninstall Helm release
	@echo "Uninstalling Helm release: $(HELM_RELEASE)"
	helm uninstall $(HELM_RELEASE) --namespace $(HELM_NAMESPACE)
	@echo "✓ Uninstalled: $(HELM_RELEASE)"

.PHONY: helm-status
helm-status: ## Show Helm release status
	helm status $(HELM_RELEASE) --namespace $(HELM_NAMESPACE)

.PHONY: helm-values
helm-values: ## Show Helm values
	@echo "Default values:"
	@cat chart/values.yaml
	@echo ""
	@echo "Deployed values (if installed):"
	@helm get values $(HELM_RELEASE) --namespace $(HELM_NAMESPACE) 2>/dev/null || echo "Not installed"

#
# Development targets
#

.PHONY: dev-start-http
dev-start-http: ## Start server in HTTP mode (local development)
	@echo "Starting server in HTTP mode..."
	python src/mcp_base_server.py --transport http --port 8000

.PHONY: dev-start-stdio
dev-start-stdio: ## Start server in stdio mode (local development)
	@echo "Starting server in stdio mode..."
	python src/mcp_base_server.py --transport stdio

.PHONY: dev-local
dev-local: ## Start test server in no-auth mode (local development)
	@echo "Starting test server in no-auth mode..."
	@echo "URL: http://localhost:8001/test"
	@echo "Health: http://localhost:8001/healthz"
	@echo ""
	python src/mcp_base_test_server.py --no-auth --port 8001

.PHONY: dev-test
dev-test: ## Run tests against local no-auth server
	@echo "Running tests against local no-auth server..."
	python test/test-mcp.py --url http://localhost:8001/test --no-auth

.PHONY: dev-test-debug
dev-test-debug: ## Run tests with debug logging against local no-auth server
	@echo "Running tests with debug logging..."
	python test/test-mcp.py --url http://localhost:8001/test --no-auth \
		--debug-log /tmp/mcp-debug.log
	@echo ""
	@echo "Debug log saved to: /tmp/mcp-debug.log"

#
# Kubernetes development targets
#

.PHONY: k8s-logs
k8s-logs: ## Show logs from deployed pods
	@echo "Logs from $(HELM_RELEASE):"
	kubectl logs -n $(HELM_NAMESPACE) -l app.kubernetes.io/name=mcp-base --tail=100 -f

.PHONY: k8s-logs-test
k8s-logs-test: ## Show logs from test server sidecar
	@echo "Test server logs from $(HELM_RELEASE):"
	kubectl logs -n $(HELM_NAMESPACE) -l app.kubernetes.io/name=mcp-base -c mcp-base-test --tail=100 -f

.PHONY: k8s-pods
k8s-pods: ## Show deployed pods
	kubectl get pods -n $(HELM_NAMESPACE) -l app.kubernetes.io/name=mcp-base

.PHONY: k8s-describe
k8s-describe: ## Describe deployed resources
	kubectl describe deployment -n $(HELM_NAMESPACE) -l app.kubernetes.io/name=mcp-base
	kubectl describe service -n $(HELM_NAMESPACE) -l app.kubernetes.io/name=mcp-base

.PHONY: k8s-port-forward
k8s-port-forward: ## Port forward to deployed service
	@echo "Port forwarding to $(HELM_RELEASE) service..."
	@echo "Access at: http://localhost:8000"
	@echo "Health: http://localhost:8000/healthz"
	@echo "MCP: http://localhost:8000/mcp"
	kubectl port-forward -n $(HELM_NAMESPACE) svc/$(HELM_RELEASE)-mcp-base 8000:8000

.PHONY: k8s-port-forward-test
k8s-port-forward-test: ## Port forward to test server
	@echo "Port forwarding to test server..."
	@echo "Access at: http://localhost:8001"
	@echo "Health: http://localhost:8001/healthz"
	@echo "Test: http://localhost:8001/test"
	kubectl port-forward -n $(HELM_NAMESPACE) svc/$(HELM_RELEASE)-mcp-base 8001:8001

.PHONY: k8s-shell
k8s-shell: ## Open shell in deployed pod
	@POD=$$(kubectl get pods -n $(HELM_NAMESPACE) -l app.kubernetes.io/name=mcp-base -o jsonpath='{.items[0].metadata.name}'); \
	echo "Opening shell in pod: $$POD"; \
	kubectl exec -it -n $(HELM_NAMESPACE) $$POD -- /bin/bash

#
# Utility targets
#

.PHONY: clean
clean: ## Clean generated files
	@echo "Cleaning generated files..."
	rm -f make.env
	@echo "✓ Cleaned"

.PHONY: help
help: ## Show this help message
	@echo "MCP Base Server - Makefile"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Development (Local No-Auth):"
	@echo "  dev-local            Start test server in no-auth mode"
	@echo "  dev-test             Run tests against local no-auth server"
	@echo "  dev-test-debug       Run tests with debug logging"
	@echo "  dev-start-http       Start server in HTTP mode"
	@echo "  dev-start-stdio      Start server in stdio mode"
	@echo ""
	@echo "Container Build:"
	@echo "  build                Build main container image"
	@echo "  build-test           Build test server image"
	@echo "  build-all            Build both images"
	@echo "  push                 Push main image to registry"
	@echo "  push-all             Push both images to registry"
	@echo ""
	@echo "Helm Chart:"
	@echo "  helm-lint            Lint Helm chart"
	@echo "  helm-template        Render chart templates"
	@echo "  helm-install         Install to Kubernetes"
	@echo "  helm-upgrade         Upgrade release"
	@echo "  helm-uninstall       Uninstall release"
	@echo ""
	@echo "Kubernetes:"
	@echo "  k8s-logs             Show logs from deployed pods"
	@echo "  k8s-pods             Show deployed pods"
	@echo "  k8s-port-forward     Port forward to service"
	@echo "  k8s-shell            Open shell in pod"
	@echo ""
	@echo "Quick Start:"
	@echo "  1. make dev-local       # Start no-auth server"
	@echo "  2. make dev-test        # Run tests"
	@echo ""
	@echo "Production:"
	@echo "  1. make config          # Generate configuration"
	@echo "  2. Edit make.env        # Customize settings"
	@echo "  3. make build-all       # Build both images"
	@echo "  4. make push-all        # Push to registry"
	@echo "  5. make helm-install    # Deploy to Kubernetes"
