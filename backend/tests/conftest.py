import os
import sys

CURRENT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

DB_PATH = os.path.abspath(os.path.join(BACKEND_DIR, "..", "test_knowledge_base.db"))
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
