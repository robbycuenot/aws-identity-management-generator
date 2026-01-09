# AWS IAM Identity Center Generator
# Multi-stage build for minimal image size

FROM python:3.13-slim-bookworm AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY scripts/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.13-slim-bookworm

# Labels are injected dynamically by the build workflow via docker/metadata-action
# See .github/workflows/build-container.yaml

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY scripts/*.py ./scripts/
COPY templates/ ./templates/
COPY config.yaml ./

# Create output directory
RUN mkdir -p /output

# Set default environment variables
ENV PYTHONUNBUFFERED=1
ENV OUTPUT_DIR=/output

# Default command - show help
ENTRYPOINT ["python", "scripts/iam_identity_center_generator.py"]
CMD ["--help"]
