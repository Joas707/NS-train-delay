"""Kleine key-value opslag: Azure Table Storage in de cloud, JSON-bestand lokaal."""
import json
import os


class Store:
    def __init__(self):
        conn = os.environ.get("AzureWebJobsStorage", "")
        self._path = os.environ.get("LOCAL_STATE_FILE")
        if conn and not conn.startswith("UseDevelopmentStorage") and not self._path:
            from azure.data.tables import TableClient  # alleen in de cloud nodig

            self._table = TableClient.from_connection_string(conn, "treinstate")
            self._table.create_table_if_not_exists()
        else:
            self._table = None
            self._path = self._path or ".state.json"

    # --- bestand
    def _load(self):
        try:
            with open(self._path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _save(self, data):
        with open(self._path, "w") as f:
            json.dump(data, f)

    # --- api
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
