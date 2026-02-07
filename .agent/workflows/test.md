---
description: how to run the test suite for CI/CD
---

1. Start the InfluxDB test container:
// turbo
`docker-compose -f docker-compose.test.yml up -d`

2. Run the pytest suite using the virtual environment:
// turbo
`.venv\Scripts\python.exe -m pytest tests/`

3. (Optional) Stop the InfluxDB test container when finished:
`docker-compose -f docker-compose.test.yml down`
