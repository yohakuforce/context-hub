# Context-Hub Dockerfile
# Target: Python 3.12 / FastAPI / uvicorn
# Works on: macOS (dev) and Windows Docker Desktop / WSL2 (production)

FROM python:3.12-slim

# System dependencies
# ffmpeg is required for Whisper audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache optimisation)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]"

# Copy application source
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Create data directories (will be overridden by volumes at runtime)
RUN mkdir -p /app/data/meetings /app/data/documents

# Ensure line endings are LF even when built on Windows
# (source files should already be LF via .gitattributes, but belt-and-suspenders)
RUN find /app/src -name "*.py" -exec sed -i 's/\r//' {} \;

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
