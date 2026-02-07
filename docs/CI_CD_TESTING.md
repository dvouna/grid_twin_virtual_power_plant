# CI/CD Testing Guide

This guide explains how to carry out tests for the Virtual Power Plant (VPP) platform, both locally and in the CI/CD pipeline.

## 1. Local Testing Environment

To run integration tests locally, you need a running InfluxDB instance and a configured Python environment.

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- Virtual environment (`.venv`) initialized

### Setup

1. **Start the Test Database**:

   ```powershell
   docker-compose -f docker-compose.test.yml up -d
   ```

   This starts InfluxDB with the credentials required by the test suite.

2. **Initialize Virtual Environment**:
   If not already done:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements_clean.txt
   pip install pytest pytest-mock pytest-asyncio
   ```

## 2. Running Tests

### Unit and Integration Tests

Run all tests using `pytest` from the project root:

```powershell
# Using the virtual environment's python module
.\.venv\Scripts\python.exe -m pytest tests/
```

### Specific Test Modules

- **System Integration**: `tests/test_system_integration.py` (Tests MCP server tools end-to-end)
- **Feature Store**: `tests/test_gridfeature_integration.py` (Tests ML feature engineering)
- **MCP Client**: `tests/test_mcp_client.py` (Tests resources and prompts)

## 3. CI/CD Pipeline

The project uses GitHub Actions for Continuous Integration.

### GitHub Actions (`.github/workflows/python-app.yml`)

The pipeline is triggered on every push to `main` or `mcp_agent`, and on pull requests to `main`. It performs:

1. **Linting**: Uses `ruff` to check code quality.
2. **Testing**: Runs the `pytest` suite.
3. **Building**: Verifies the Docker image builds correctly.

### Cloud Build (`cloudbuild.yaml`)

Cloud Build handles the deployment to Google Cloud Run:

1. Builds the production container image.
2. Pushes the image to Google Container Registry.
3. Deploys to Cloud Run with appropriate environment variables and memory settings.

## 4. Troubleshooting

- **InfluxDB Connection Errors**: Ensure the container is running and healthy: `docker ps`.
- **Module Not Found**: Ensure `PYTHONPATH` includes `src`. This is handled automatically by `pytest.ini`.
- **Missing Model Files**: Ensure `xgboost_smart_ml.ubj` and `model_features.txt` are in the project root or specified in environment variables.
