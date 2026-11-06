"""Start Stellavex: the game and its API on one server.   python run.py [--port 8000]"""
import argparse
from pathlib import Path

import uvicorn

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8000)
a = ap.parse_args()
print("Stellavex is running at http://%s:%d" % (a.host, a.port))
uvicorn.run("main:app", app_dir=str(Path(__file__).parent / "backend"), host=a.host, port=a.port)
