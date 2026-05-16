# Context-Hub Dockerfile
# Target: Python 3.12 / FastAPI / uvicorn
# Works on: macOS (dev) and Windows Docker Desktop / WSL2 (production)
#
# LLM: Claude Code CLI / Codex CLI are installed on the host and called via
# subprocess from within the container (mounted host PATH or docker exec).
# No Anthropic/OpenAI SDK required.
#
# Embedding: BGE-M3 runs locally via FlagEmbedding.
# Model (~2.3GB) is downloaded on first startup and cached in a named volume.

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

# Pre-download BGE-M3 model into image cache layer.
# On first `docker compose up` this layer is built once and cached.
# Production: model lives in the bge-m3-cache volume, so this RUN
# only runs during `docker build`; the volume takes precedence at runtime
# if already populated.
ENV HF_HOME=/root/.cache/huggingface
RUN python -c "\
from FlagEmbedding import BGEM3FlagModel; \
BGEM3FlagModel('BAAI/bge-m3', use_fp16=True); \
print('BGE-M3 model cached successfully')" || \
    echo "BGE-M3 pre-download skipped (will download at first run)"

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
