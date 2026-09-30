"""Start AlgoCompare:  python run.py   then open http://localhost:8000"""
import os

from backend.app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
