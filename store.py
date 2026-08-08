"""Storage abstraction.

If SUPABASE_URL and SUPABASE_KEY are set, uses Supabase (Postgres). Otherwise falls back to an
in-memory store so the app always runs. Both expose the same interface, so the rest of the app
never knows which backend is active.
"""
import os
import threading
from typing import Optional, List

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


# ------------------------------------------------------------------ in-memory
class InMemoryStore:
    name = "in-memory"

    def __init__(self):
        self._lock = threading.Lock()
        self.applications = {}
        self.cases = {}

    def create_application(self, rec: dict): 
        with self._lock: self.applications[rec["id"]] = rec
    def update_application(self, rec: dict):
        with self._lock: self.applications[rec["id"]] = rec
    def get_application(self, app_id: str) -> Optional[dict]:
        return self.applications.get(app_id)
    def list_applications(self) -> List[dict]:
        return list(self.applications.values())

    def create_case(self, case: dict):
        with self._lock: self.cases[case["case_id"]] = case
    def update_case(self, case: dict):
        with self._lock: self.cases[case["case_id"]] = case
    def get_case(self, case_id: str) -> Optional[dict]:
        return self.cases.get(case_id)
    def list_cases(self) -> List[dict]:
        return list(self.cases.values())

    def clear(self):
        with self._lock:
            self.applications.clear()
            self.cases.clear()


# ------------------------------------------------------------------ supabase
class SupabaseStore:
    name = "supabase"

    def __init__(self):
        from supabase import create_client
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # applications
    def _app_row(self, r: dict) -> dict:
        return {"id": r["id"], "name": r["profile"].get("name"), "city": r["profile"].get("city"),
                "level": r["risk"]["level"], "confidence": r["risk"]["confidence"],
                "status": r["status"], "case_id": r.get("case_id"),
                "created_at": r["created_at"], "profile": r["profile"], "risk": r["risk"],
                "history": r["history"]}

    def _app_from_row(self, row: dict) -> dict:
        return {"id": row["id"], "profile": row["profile"], "risk": row["risk"],
                "status": row["status"], "case_id": row.get("case_id"),
                "created_at": row["created_at"], "history": row["history"]}

    def create_application(self, rec: dict):
        self.client.table("applications").insert(self._app_row(rec)).execute()
    def update_application(self, rec: dict):
        self.client.table("applications").update(self._app_row(rec)).eq("id", rec["id"]).execute()
    def get_application(self, app_id: str) -> Optional[dict]:
        res = self.client.table("applications").select("*").eq("id", app_id).execute()
        return self._app_from_row(res.data[0]) if res.data else None
    def list_applications(self) -> List[dict]:
        res = self.client.table("applications").select("*").order("created_at", desc=True).execute()
        return [self._app_from_row(r) for r in (res.data or [])]

    # cases
    def create_case(self, case: dict):
        self.client.table("cases").insert(case).execute()
    def update_case(self, case: dict):
        self.client.table("cases").update(case).eq("case_id", case["case_id"]).execute()
    def get_case(self, case_id: str) -> Optional[dict]:
        res = self.client.table("cases").select("*").eq("case_id", case_id).execute()
        return res.data[0] if res.data else None
    def list_cases(self) -> List[dict]:
        res = self.client.table("cases").select("*").execute()
        return res.data or []

    def clear(self):
        self.client.table("cases").delete().neq("case_id", "").execute()
        self.client.table("applications").delete().neq("id", "").execute()


# ------------------------------------------------------------------ factory
def get_store():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            store = SupabaseStore()
            print("[store] using Supabase")
            return store
        except Exception as e:
            print(f"[store] Supabase init failed ({e}); falling back to in-memory")
    print("[store] using in-memory")
    return InMemoryStore()