# --- Builder stage: compile native dependencies (S22) ---
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY excel-addin/backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# --- Final stage: slim image without compiler (S17, S22) ---
FROM python:3.12-slim

WORKDIR /app

# Install only runtime dependency for asyncpg (no gcc).
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder.
COPY --from=builder /install /usr/local

# Copy shared libraries that the backend depends on.
# NOTE: Build context is projects/ (set by docker-compose),
# so all COPY paths are relative to the projects/ directory.
COPY fortnox-mcp /app/fortnox-mcp
COPY sie-pipeline /app/sie-pipeline

# Copy backend code.
COPY excel-addin/backend /app/backend

# Set Python path so imports resolve across projects.
ENV PYTHONPATH="/app/backend:/app/fortnox-mcp:/app/sie-pipeline"

WORKDIR /app/backend

# SECURITY (S17): Run as non-root user.
RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
