# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV PYTHONPATH=/app/src
ENV PORT=8080

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements_docker.txt .
RUN pip install --no-cache-dir -r requirements_docker.txt

# Copy the rest of the application code
COPY . .

# Cloud Run uses the PORT environment variable
EXPOSE ${PORT}

# Run the MCP server with SSE transport by default
# This allows the server to be reached over the network on Cloud Run
CMD ["python", "-m", "vpp.mcp.mcp_server"]
