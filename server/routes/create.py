"""Create database tables.

Supports running either as a module:
  python3 -m routes.create
or as a script from the server directory:
  python3 ./routes/create.py
"""

from __future__ import annotations

import sys
from pathlib import Path


# When executed as a script, Python puts ./routes on sys.path which breaks
# absolute imports like `from routes...`. Ensure the server root is on sys.path.
if __package__ in (None, ""):
	server_root = Path(__file__).resolve().parents[1]
	sys.path.insert(0, str(server_root))


from routes.schema import create_tables


if __name__ == "__main__":
	create_tables()