import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app

if __name__ == "__main__":
    app.run(port=5050, debug=False)
