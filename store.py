"""Small key-value store: Azure Table Storage in the cloud, a JSON file locally."""
import json
import os


class Store:
    def __init__(self):
        # Flex Consumption has no AzureWebJobsStorage connection string (it uses identity-based
        # access), so the state table gets its own setting. AzureWebJobsStorage is a fallback.
        conn = os.environ.get("STATE_STORAGE_CONNECTION") or os.environ.get("AzureWebJobsStorage", "")
        self._path = os.environ.get("LOCAL_STATE_FILE")
        if conn and not conn.startswith("UseDevelopmentStorage") and not self._path:
            from azure.data.tables import TableClient  # only needed in the cloud

            self._table = TableClient.from_connection_string(conn, "trainstate")
            self._table.create_table_if_not_exists()
        else:
            self._table = None
            self._path = self._path or ".state.json"

    # --- file backend
    def _load(self):
        try:
            with open(self._path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _save(self, data):
        with open(self._path, "w") as f:
            json.dump(data, f)

    # --- public API
    def get(self, key):
        if self._table is None:
            return self._load().get(key)
        try:
            return json.loads(self._table.get_entity("s", key)["v"])
        except Exception:
            return None

    def set(self, key, value):
        if self._table is None:
            data = self._load()
            data[key] = value
            self._save(data)
        else:
            self._table.upsert_entity({"PartitionKey": "s", "RowKey": key, "v": json.dumps(value)})

    def delete(self, key):
        if self._table is None:
            data = self._load()
            data.pop(key, None)
            self._save(data)
        else:
            try:
                self._table.delete_entity("s", key)
            except Exception:
                pass


_DELETED = object()


class OverlayStore:
    """Reads fall through to the real store; writes stay in memory (used for dry runs)."""

    def __init__(self, real):
        self._real = real
        self._local = {}

    def get(self, key):
        if key in self._local:
            v = self._local[key]
            return None if v is _DELETED else v
        return self._real.get(key)

    def set(self, key, value):
        self._local[key] = value

    def delete(self, key):
        self._local[key] = _DELETED
