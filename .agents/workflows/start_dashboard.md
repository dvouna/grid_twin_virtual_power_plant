---
description: how to start the Streamlit dashboard
---

Always launch Streamlit from the `.venv` Python environment, NOT the system Python.
The system Python 3.9 lacks `mcp` support (requires 3.10+) and is missing other project packages.

1. Make sure the venv is active and all dependencies are installed:
```
.\.venv\Scripts\pip install -r requirements.txt
```

// turbo
2. Launch the dashboard using the venv's Streamlit binary:
```
.\.venv\Scripts\streamlit run dashboard\app.py
```
