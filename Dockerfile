FROM python:3.11-slim

# 1. Standardize Environment Variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PORT=8080 \
    MODEL_PATH=models/xgboost_smart_ml.ubj \
    FEATURES_PATH=models/model_features.txt

WORKDIR /app

# 2. Optimized System Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    librdkafka-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 3. Install Python Dependencies
COPY requirements_docker.txt .
RUN pip install --no-cache-dir -r requirements_docker.txt

# 4. Security: Create non-privileged user
RUN useradd -m mcpuser

# 5. Copy Code (Explicitly to ensure build fails if files are missing)
# Ensure files are owned by the non-privileged user
COPY --chown=mcpuser:mcpuser src/ ./src/
COPY --chown=mcpuser:mcpuser models/ ./models/
COPY --chown=mcpuser:mcpuser requirements_docker.txt .

USER mcpuser

EXPOSE 8080

# 6. Use 'exec' form for proper signal handling
# This ensures Python handles the termination signal from Cloud Run
CMD ["python", "-m", "vpp.mcp.mcp_server"]