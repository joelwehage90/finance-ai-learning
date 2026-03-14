FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for asyncpg
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared libraries that the backend depends on
COPY ../../fortnox-mcp /app/fortnox-mcp
COPY ../../sie-pipeline /app/sie-pipeline

# Copy backend code
COPY . /app/backend

# Set Python path so imports resolve across projects
ENV PYTHONPATH="/app/backend:/app/fortnox-mcp:/app/sie-pipeline"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
