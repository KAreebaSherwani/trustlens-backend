"""TrustLens API — FastAPI app wiring, service logic and routes."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import OnboardingIn, OfficerAction, Clarification
from engine import assess, DEMO_MODE, GEMINI_API_KEY
from store import get_store
from seed import seed

AUTO_EDD_LEVELS = set(os.getenv("AUTO_EDD_LEVELS", "high").lower().split(","))

app = FastAPI(title="TrustLens API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STORE = get_store()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def plant_state(app_status: str, level: str) -> str:
    return {
        "active": "healthy", "needs_attention": "needs_attention", "in_edd": "under_review",
        "clarification_requested": "review_requested", "escalated": "under_review",
        "approved": "bloomed", "rejected": "declined",
    }.get(app_status, "healthy")


# ------------------------------------------------------------------ service logic
def open_case(record: dict, reason: str, by: str) -> dict:
    case_id = new_id("edd")
    case = {"case_id": case_id, "application_id": record["id"],
            "applicant_name": record["profile"].get("name"), "risk_level": record["risk"]["level"],
            "status": "pending_review", "reason": reason, "created_at": now(),
            "history": [{"status": "pending_review", "at": now(), "by": by, "note": reason}]}
    STORE.create_case(case)
    record["case_id"] = case_id
    record["status"] = "in_edd"
    record["history"].append({"status": "in_edd", "at": now(), "by": by,
                              "note": "Routed to Enhanced Due Diligence queue."})
    STORE.update_application(record)
    return case


def create_application(p: OnboardingIn) -> dict:
    risk = assess(p)
    app_id = new_id("app")
    status = "in_edd" if risk.level in AUTO_EDD_LEVELS else ("needs_attention" if risk.level == "medium" else "active")
    record = {"id": app_id, "profile": p.model_dump(), "risk": risk.model_dump(), "status": status,
              "case_id": None, "created_at": now(),
              "history": [{"status": status, "at": now(), "by": "system",
                           "note": f"Assessed {risk.level.upper()} ({risk.confidence}% confidence)."}]}
    STORE.create_application(record)
    if risk.level in AUTO_EDD_LEVELS:
        open_case(record, reason=risk.conclusion, by="system")
    record["plant_state"] = plant_state(record["status"], risk.level)
    return record


# ------------------------------------------------------------------ routes
@app.get("/")
def root():
    return {"service": "TrustLens API", "status": "ok", "store": STORE.name,
            "engine": "deterministic" if (DEMO_MODE or not GEMINI_API_KEY) else "gemini",
            "demo_mode": DEMO_MODE, "auto_edd_levels": sorted(AUTO_EDD_LEVELS)}


@app.post("/api/onboarding")
def submit_onboarding(payload: OnboardingIn):
    r = create_application(payload)
    return {"application_id": r["id"], "risk": r["risk"], "status": r["status"],
            "plant_state": r["plant_state"], "case_id": r["case_id"]}


@app.get("/api/applications")
def list_applications():
    items = []
    for r in STORE.list_applications():
        items.append({"id": r["id"], "name": r["profile"].get("name"), "city": r["profile"].get("city"),
                      "level": r["risk"]["level"], "confidence": r["risk"]["confidence"],
                      "status": r["status"], "case_id": r.get("case_id"),
                      "plant_state": plant_state(r["status"], r["risk"]["level"]), "created_at": r["created_at"]})
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"count": len(items), "applications": items}


@app.get("/api/applications/{app_id}")
def get_application(app_id: str):
    r = STORE.get_application(app_id)
    if not r:
        raise HTTPException(404, "Application not found")
    r = dict(r)
    r["plant_state"] = plant_state(r["status"], r["risk"]["level"])
    r["case"] = STORE.get_case(r["case_id"]) if r.get("case_id") else None
    return r


@app.post("/api/applications/{app_id}/route-edd")
def route_to_edd(app_id: str):
    r = STORE.get_application(app_id)
    if not r:
        raise HTTPException(404, "Application not found")
    if r.get("case_id"):
        return {"case_id": r["case_id"], "status": STORE.get_case(r["case_id"])["status"]}
    case = open_case(r, reason="Manually routed for review by compliance officer.", by="officer")
    return {"case_id": case["case_id"], "status": case["status"],
            "plant_state": plant_state(r["status"], r["risk"]["level"])}


@app.post("/api/applications/{app_id}/clarify")
def submit_clarification(app_id: str, body: Clarification):
    r = STORE.get_application(app_id)
    if not r:
        raise HTTPException(404, "Application not found")
    cid = r.get("case_id")
    if not cid:
        raise HTTPException(400, "No open case for this application")
    case = STORE.get_case(cid)
    case["status"] = "pending_review"
    case["history"].append({"status": "pending_review", "at": now(), "by": "applicant",
                            "note": f"Clarification: {body.message}"})
    STORE.update_case(case)
    r["status"] = "in_edd"
    r["history"].append({"status": "in_edd", "at": now(), "by": "applicant",
                        "note": "Clarification submitted; returned to review."})
    STORE.update_application(r)
    return {"case_id": cid, "status": case["status"]}


@app.get("/api/edd/queue")
def edd_queue():
    q = [c for c in STORE.list_cases() if c["status"] == "pending_review"]
    q.sort(key=lambda c: c["created_at"])
    return {"count": len(q), "queue": q}


@app.post("/api/cases/{case_id}/action")
def officer_action(case_id: str, body: OfficerAction):
    case = STORE.get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    r = STORE.get_application(case["application_id"])
    mapping = {"approve": ("approved", "approved"), "reject": ("rejected", "rejected"),
               "escalate": ("escalated", "escalated"),
               "request_clarification": ("clarification_requested", "clarification_requested")}
    case_status, app_status = mapping[body.action]
    stamp, note = now(), (body.note or f"Officer action: {body.action}.")
    case["status"] = case_status
    case["history"].append({"status": case_status, "at": stamp, "by": body.officer, "note": note})
    STORE.update_case(case)
    r["status"] = app_status
    r["history"].append({"status": app_status, "at": stamp, "by": body.officer, "note": note})
    STORE.update_application(r)
    return {"case_id": case_id, "case_status": case_status, "application_status": app_status,
            "plant_state": plant_state(r["status"], r["risk"]["level"])}


@app.get("/api/dashboard")
def dashboard():
    apps = STORE.list_applications()
    dist = {"low": 0, "medium": 0, "high": 0}
    status_counts, transitions = {}, []
    for r in apps:
        dist[r["risk"]["level"]] += 1
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
        for h in r["history"]:
            transitions.append({"application_id": r["id"], "name": r["profile"].get("name"),
                                "status": h["status"], "at": h["at"], "by": h["by"]})
    transitions.sort(key=lambda t: t["at"])
    cases = STORE.list_cases()
    return {"total_applications": len(apps), "risk_distribution": dist, "status_counts": status_counts,
            "edd_queue_open": len([c for c in cases if c["status"] == "pending_review"]),
            "edd_resolved": len([c for c in cases if c["status"] in ("approved", "rejected", "escalated")]),
            "before_after_review": {
                "pending_before_review": len([r for r in apps if r["status"] in ("in_edd", "needs_attention")]),
                "resolved_after_review": len([r for r in apps if r["status"] in ("approved", "rejected", "escalated")])},
            "transitions": transitions}


@app.post("/api/reset")
def reset():
    STORE.clear()
    seed(create_application)
    return {"status": "reseeded", "applications": len(STORE.list_applications())}


@app.on_event("startup")
def _startup():
    if not STORE.list_applications():
        seed(create_application)