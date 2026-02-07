FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PORT=8080 \
    # Explicitly set Model paths to MATCH default ENV vars in mcp_server.py
    MODEL_PATH=models/xgboost_smart_ml.ubj \
    FEATURES_PATH=models/model_features.txt

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements_docker.txt .
RUN pip install --no-cache-dir -r requirements_docker.txt

# Copy source code and models
# COPY . . copies everything not in .dockerignore
COPY . .

# Verification step (Optional but good for debugging build logs)
RUN ls -la models/

EXPOSE 8080

CMD ["python", "-m", "vpp.mcp.mcp_server"]