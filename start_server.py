"""
Cloud entry point — used by Render / Railway / any cloud host.
Changes to backend/ directory and starts uvicorn on the PORT env variable.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

# Set PROJECT_ROOT so main.py can always find the frontend folder
os.environ["PROJECT_ROOT"] = PROJECT_ROOT

os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

import uvicorn

port = int(os.environ.get("PORT", 8000))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
