"""Persist EA tokens + selected league in a JSON file on a Docker volume."""
import json
import os
import threading

DATA_DIR = os.environ.get("DATA_DIR", "/data")


class TokenStore:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(DATA_DIR, "ea_state.json")
        self._lock = threading.Lock()

    def load(self) -> dict | None:
        try:
            with open(self.path) as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def save(self, state: dict):
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, self.path)

    def update(self, **fields):
        with self._lock:
            state = self.load() or {}
            state.update(fields)
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, self.path)

    def clear(self):
        with self._lock:
            try:
                os.remove(self.path)
            except FileNotFoundError:
                pass


store = TokenStore()
