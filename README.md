# TrustLens — Backend

AI-driven customer risk profiling for digital wallet onboarding (Track 2 · Mobilink).
FastAPI · Gemini reasoning · Supabase (Postgres) · deploys on Render.

## Files
```
main.py        FastAPI app, service logic, all routes
engine.py      risk engine (Gemini + deterministic fallback)
store.py       storage layer (Supabase, in-memory fallback)
models.py      pydantic models
seed.py        demo applicants
supabase_schema.sql   run once in Supabase SQL Editor
render.yaml    Render blueprint
requirements.txt / .env.example
```

## Run locally
```bash
pip install -r requirements.txt
cp .env.example .env      # fill in keys
uvicorn main:app --reload --port 8000
# open http://localhost:8000  and  http://localhost:8000/docs
```

## Supabase (3 steps)
1. Create a project at supabase.com.
2. SQL Editor → paste `supabase_schema.sql` → Run.
3. Settings → API → copy `Project URL` and a key into `SUPABASE_URL` / `SUPABASE_KEY`.
   (Use the **service_role** key on the server so RLS never blocks writes.)

If `SUPABASE_URL`/`SUPABASE_KEY` are set it uses Supabase; if not, it runs in-memory automatically.

## Gemini
Set `GEMINI_API_KEY` (and optionally `GEMINI_MODEL`). Leave `DEMO_MODE=false` for live reasoning.
Set `DEMO_MODE=true` to force the reproducible deterministic engine (recommended for the final video).

## Deploy on Render
1. Push this folder to GitHub.
2. Render → New → Blueprint → pick the repo (it reads `render.yaml`), **or** New → Web Service with:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Add env vars: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` (and `DEMO_MODE`, `AUTO_EDD_LEVELS`).
4. Give Areeb the live URL as the frontend base URL.

## API contract (build the frontend against this)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/onboarding` | submit profile → risk assessment (+ EDD case if flagged) |
| POST | `/api/documents/analyze` | upload CNIC/doc image → OCR extract + cross-check vs declared data |
| GET | `/api/applications` | officer list / garden grid |
| GET | `/api/applications/{id}` | full detail + reasoning trail + case |
| POST | `/api/applications/{id}/route-edd` | officer pulls a medium case into EDD |
| POST | `/api/applications/{id}/clarify` | applicant sends clarification |
| GET | `/api/edd/queue` | pending EDD cases |
| POST | `/api/cases/{id}/action` | approve / request_clarification / escalate / reject |
| GET | `/api/dashboard` | volume, risk distribution, EDD queue, before/after |
| POST | `/api/reset` | reseed demo data |

`plant_state` values for the garden: `healthy` 🌳 · `needs_attention` 🌾 · `under_review` 🪴 · `review_requested` 🌿 · `bloomed` 🌸 · `declined`.

### Document analysis (OCR via Gemini vision)
`POST /api/documents/analyze` — `multipart/form-data`:
- `file` (required): the CNIC / income / business document image
- `document_type` (optional): `cnic` (default) / `income_proof` / `business_doc`
- `application_id` (optional): if given, cross-checks the extracted ID against declared data

Returns `{ extracted:{name,cnic,father_name,date_of_birth,address,date_of_expiry,raw_text}, checks:[{field,declared,extracted,verdict}], match_summary }`.
On a name/CNIC **mismatch** it adds a "Document verification" signal (inconsistent) to the risk trail and auto-routes the application to EDD. In `DEMO_MODE` it returns a fixed sample extraction so the flow is reproducible without a live call.

## Demo personas (reproducible in DEMO_MODE)
| Profile | Result |
|---|---|
| Salaried, income ≈ transactions | LOW → healthy |
| Self-employed shop, tx ≫ income, customer payments | MEDIUM → needs_attention |
| Student/unemployed, tx ≫ income, personal | HIGH → auto-EDD → under_review |


## System Architecture

```mermaid
flowchart TD
    APP(["👤 Applicant (Kamran)"]):::actor
    OFF(["🧑‍💼 Compliance Officer"]):::actor

    subgraph FE["📱 Frontend — Mobile App · Garden UI"]
        ONB["Onboarding flow<br/>KYC fields + CNIC photo"]
        DASH["Officer Dashboard<br/>Trust Ecosystem + EDD queue"]
    end

    subgraph BE["⚙️ Backend — FastAPI on Render"]
        API["API layer<br/>/api/onboarding<br/>/api/documents/analyze"]
        DOC["Document OCR<br/>Gemini 3.6 Flash vision<br/>cross-check vs declared"]
        ENG{{"Risk Engine<br/>multi-signal reasoning"}}
        GEM["Gemini 3.6 Flash<br/>relational reasoning"]
        DET["Deterministic fallback<br/>reproducible"]
        DEC{"Risk level?"}
        LOW["Active · healthy 🌳"]
        MED["Needs attention 🌾"]
        CASE["Create EDD case<br/>status: pending_review 🪴"]
        ACT["Officer actions<br/>approve · clarify · escalate · reject"]
        AGG["Dashboard aggregation<br/>volume · distribution · before/after"]
    end

    DB[("🗄️ Supabase · Postgres<br/>applications · cases")]:::db

    %% ---- onboarding input ----
    APP --> ONB
    ONB --> API
    API --> DOC
    DOC -->|CNIC mismatch| ENG
    API --> ENG

    %% ---- AI risk-profiling ----
    ENG --> GEM
    ENG --> DET
    GEM --> DEC
    DET --> DEC

    %% ---- decision / flagging ----
    DEC -->|Low| LOW
    DEC -->|Medium| MED
    DEC -->|High| CASE

    %% ---- data storage ----
    ENG --> DB
    LOW --> DB
    MED --> DB
    CASE --> DB

    %% ---- EDD routing + dashboard output ----
    DB --> AGG
    AGG --> DASH
    CASE --> DASH
    DASH --> OFF
    OFF --> ACT
    ACT --> DB

    classDef actor fill:#1b4332,stroke:#081c15,color:#ffffff
    classDef db fill:#40916c,stroke:#1b4332,color:#ffffff