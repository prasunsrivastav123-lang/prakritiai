import sqlite3
import json
import requests
import time
import threading
import logging
from datetime import datetime
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class OfflineSyncEngine:
    def __init__(self, db_path: str = "field_offline.db", server_url: str = "http://localhost:8000/api"):
        self.db_path = db_path
        self.server_url = server_url
        self.is_syncing = False
        self.backoff_seconds = 60  # Exponential backoff start
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;") # Crash resilience
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS pending_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT, lat REAL, lon REAL, report_type TEXT, 
                description TEXT, photo_path TEXT, timestamp TEXT, synced INTEGER DEFAULT 0)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS cached_routes (
                route_id TEXT PRIMARY KEY, depot TEXT, village TEXT, geometry_json TEXT, last_updated TEXT)''')
            conn.commit()

    def save_report_offline(self, lat: float, lon: float, report_type: str, description: str, photo_path: str = None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO pending_reports (lat, lon, report_type, description, photo_path, timestamp)
                              VALUES (?, ?, ?, ?, ?, ?)''',
                           (lat, lon, report_type, description, photo_path, datetime.utcnow().isoformat()))
            conn.commit()

    def _get_unsynced_reports(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.cursor().execute("SELECT * FROM pending_reports WHERE synced = 0 LIMIT 50")]

    def _mark_as_synced(self, report_ids: List[int]):
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().executemany("UPDATE pending_reports SET synced = 1 WHERE id = ?", [(rid,) for rid in report_ids])
            conn.commit()

    def _check_network_reachable(self) -> bool:
        try:
            return requests.get(f"{self.server_url}/health", timeout=3.0).status_code == 200
        except requests.exceptions.RequestException:
            return False

    def _push_reports(self) -> bool:
        reports = self._get_unsynced_reports()
        if not reports: return True
        try:
            response = requests.post(f"{self.server_url}/field-reports/batch", json={"reports": reports}, timeout=10.0)
            # FIX: FastAPI returns 200 by default, not 201
            if response.status_code in (200, 201):
                self._mark_as_synced([r['id'] for r in reports])
                logging.info(f"Successfully bulk-synced {len(reports)} offline reports.")
                self.backoff_seconds = 60
                return True
        except requests.exceptions.RequestException:
            return False

    def _pull_routes(self) -> bool:
        try:
            response = requests.get(f"{self.server_url}/routes/active", timeout=10.0)
            if response.status_code == 200:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    for route in response.json().get('routes', []):
                        cursor.execute('''INSERT OR REPLACE INTO cached_routes VALUES (?, ?, ?, ?, ?)''',
                                      (route['route_id'], route['depot'], route['village'], json.dumps(route['geometry']), datetime.utcnow().isoformat()))
                    conn.commit()
                return True
        except requests.exceptions.RequestException:
            return False

    def start_background_sync(self):
        def sync_loop():
            while True:
                if self._check_network_reachable():
                    if not self.is_syncing:
                        self.is_syncing = True
                        self._push_reports()
                        self._pull_routes()
                        self.is_syncing = False
                else:
                    logging.info(f"Network offline. Backoff: {self.backoff_seconds}s")
                time.sleep(self.backoff_seconds)
                self.backoff_seconds = min(self.backoff_seconds * 2, 300)
        threading.Thread(target=sync_loop, daemon=True).start()