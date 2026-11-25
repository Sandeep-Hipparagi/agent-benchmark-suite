# ==========================================
# Build Stage
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir --upgrade pip build hatchling

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Build wheel
RUN python -m build --wheel --no-isolation

# ==========================================
# Runtime Stage
# ==========================================
FROM python:3.12-slim AS runner

WORKDIR /app

# Create non-root user
RUN groupadd -r agentbench && useradd -r -g agentbench -d /app -s /sbin/nologin agentbench && \
    chown -R agentbench:agentbench /app

# Copy wheel from builder and install
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Switch to non-root user
USER agentbench

# OCI labels for GitHub Packages repository linking
LABEL org.opencontainers.image.source="https://github.com/Sandeep-Hipparagi/agent-benchmark-suite" \
      org.opencontainers.image.description="Unified reproducible benchmark harness for agentic AI: token compression, provenance, routing, and policy leaderboards with CI-enforced drift checks" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.title="Agent Benchmark Suite" \
      org.opencontainers.image.version="0.1.0"

ENTRYPOINT ["agent-bench"]
CMD ["--help"]