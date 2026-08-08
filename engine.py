"""Risk reasoning engine: live Gemini primary, deterministic fallback.

The deterministic engine is (a) the fallback if a live Gemini call errors mid-demo, and
(b) a fully reproducible mode via DEMO_MODE=true for recording the final video.
Both engines return the SAME RiskResult shape, so downstream code never changes.
"""
import os
import json
from models import OnboardingIn, Signal, RiskResult, Level

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")


# ------------------------------------------------------------------ deterministic engine
def deterministic_assess(p: OnboardingIn) -> RiskResult:
    income = float(p.monthly_income or 0)
    tx = float(p.expected_monthly_transactions or 0)
    emp = (p.employment_type or "").lower()
    purpose = (p.account_purpose or "").lower()
    biz = (p.business_type or "").strip()

    ratio = (tx / income) if income > 0 else (999.0 if tx > 0 else 0.0)
    is_business = any(k in emp for k in ["self", "business", "shop", "merchant", "trader"]) or bool(biz)
    business_purpose = any(k in purpose for k in ["customer", "business", "payment", "sales", "merchant", "receipt"])
    personal_purpose = any(k in purpose for k in ["personal", "saving", "family", "salary", "remit"])
    low_income_emp = any(k in emp for k in ["student", "unemploy", "house", "no job", "dependent"])

    score = 0
    signals = []

    signals.append(Signal(
        label="Declared income",
        value=f"Rs. {int(income):,}/mo" if income else "Not provided",
        verdict="consistent" if income else "attention",
        note="Baseline used to cross-check transaction and purpose signals.",
    ))

    if ratio >= 5:
        if is_business and business_purpose:
            score += 30
            signals.append(Signal(
                label="Income vs expected transactions",
                value=f"~{ratio:.0f}x declared income", verdict="attention",
                note=("Throughput far exceeds personal income, but a business receiving customer "
                      "payments can plausibly process revenue above personal earnings. Worth "
                      "confirming receipts — not inherently suspicious."),
            ))
        else:
            score += 65
            signals.append(Signal(
                label="Income vs expected transactions",
                value=f"~{ratio:.0f}x declared income", verdict="inconsistent",
                note=("Expected volume greatly exceeds declared income with no business purpose to "
                      "explain it. Warrants enhanced due diligence."),
            ))
    elif ratio >= 2:
        score += 15
        signals.append(Signal(label="Income vs expected transactions",
                              value=f"~{ratio:.1f}x declared income", verdict="attention",
                              note="Somewhat above declared income; acceptable but noted."))
    else:
        signals.append(Signal(label="Income vs expected transactions",
                              value=f"~{ratio:.1f}x declared income" if income else "n/a",
                              verdict="consistent", note="In line with declared income."))

    if low_income_emp and income > 150000:
        score += 25
        signals.append(Signal(label="Employment vs income",
                              value=f"{p.employment_type} · Rs. {int(income):,}/mo", verdict="inconsistent",
                              note="High declared income is unusual for the stated employment type."))
    else:
        signals.append(Signal(label="Employment vs income", value=(p.employment_type or "Not provided"),
                              verdict="consistent", note="Income is consistent with stated occupation."))

    if personal_purpose and tx > 500000:
        score += 20
        signals.append(Signal(label="Account purpose vs volume",
                              value=f"{p.account_purpose} · Rs. {int(tx):,}/mo", verdict="attention",
                              note="Personal-use account with unusually high expected volume."))
    else:
        signals.append(Signal(label="Account purpose vs volume", value=(p.account_purpose or "Not provided"),
                              verdict="consistent", note="Stated purpose is consistent with expected activity."))

    score = max(0, min(100, score))
    level: Level = "high" if score > 65 else ("medium" if score >= 30 else "low")
    confidence = min(95, 70 + int(abs(score - 45) * 0.35))

    if level == "high":
        conclusion = ("Multiple signals conflict — expected activity is not supported by the declared "
                      "profile. Recommend enhanced due diligence before activation.")
    elif level == "medium":
        conclusion = ("Not inherently suspicious, but one or more signals do not fully align (chiefly "
                      "transaction expectations vs declared income). Additional information should be "
                      "reviewed before activation.")
    else:
        conclusion = "All signals are mutually consistent. No indicators warranting review. Routine processing."

    return RiskResult(level=level, confidence=confidence, signals=signals,
                      conclusion=conclusion, engine="deterministic")


# ------------------------------------------------------------------ Gemini engine
GEMINI_PROMPT = """You are TrustLens, a bank compliance risk-reasoning engine for digital wallet
onboarding in Pakistan. Reason across ALL of the applicant's signals TOGETHER — never score fields
in isolation.

Cross-reference explicitly:
- declared income vs expected monthly transactions
- employment/occupation vs declared income
- account purpose vs expected transaction volume
- employment vs account purpose

Nuance: a legitimate business account (self-employed, "receive customer payments") routinely
processes revenue far above the owner's personal income. Do NOT treat high throughput as suspicious
on its own — weigh it against the declared occupation and purpose. Risk rises only when signals
cannot plausibly explain each other.

Assign overall risk "low" | "medium" | "high" with confidence 0-100. For EACH signal give a verdict
("consistent" | "attention" | "inconsistent") and a one-line reason. Then a short plain-language
conclusion. Never output a silent score without reasons.

Applicant profile (JSON):
{profile}

Return ONLY valid JSON, no markdown, exactly:
{{"level":"low|medium|high","confidence":0-100,
"signals":[{{"label":"...","value":"...","verdict":"consistent|attention|inconsistent","note":"..."}}],
"conclusion":"..."}}"""


def gemini_assess(p: OnboardingIn) -> RiskResult:
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = GEMINI_PROMPT.format(profile=json.dumps(p.model_dump(), ensure_ascii=False))
    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    raw = (resp.text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"): raw.rfind("}") + 1]
    data = json.loads(raw)
    return RiskResult(level=data["level"], confidence=int(data.get("confidence", 75)),
                      signals=[Signal(**s) for s in data["signals"]],
                      conclusion=data["conclusion"], engine="gemini")


def assess(p: OnboardingIn) -> RiskResult:
    if DEMO_MODE or not GEMINI_API_KEY:
        return deterministic_assess(p)
    try:
        return gemini_assess(p)
    except Exception as e:
        r = deterministic_assess(p)
        r.engine = f"deterministic (gemini fallback: {type(e).__name__})"
        return r


# ------------------------------------------------------------------ document / OCR (multimodal)
DOC_PROMPT = """You are a KYC document reader for Pakistani CNIC cards and financial/business
documents. Read the attached image and extract the fields. Return ONLY valid JSON, no markdown:
{{"document_type":"{document_type}","name":null,"cnic":null,"father_name":null,
"date_of_birth":null,"address":null,"date_of_expiry":null,"raw_text":null}}
Use null for any field not present. cnic format: 00000-0000000-0. dates as YYYY-MM-DD if possible.
Put any other legible text into raw_text."""


def _demo_document(document_type: str) -> dict:
    return {"document_type": document_type, "name": "Kamran Ahmed", "cnic": "37405-3333333-3",
            "father_name": "Ahmed Ali", "date_of_birth": "1992-05-14",
            "address": "Liaquat Bazaar, Rawalpindi", "date_of_expiry": "2031-05-14",
            "raw_text": "PAKISTAN NATIONAL IDENTITY CARD", "engine": "demo"}


def extract_document(image_bytes: bytes, mime_type: str = "image/jpeg",
                     document_type: str = "cnic") -> dict:
    if DEMO_MODE or not GEMINI_API_KEY:
        return _demo_document(document_type)
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                      DOC_PROMPT.format(document_type=document_type)],
        )
        raw = (resp.text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("{"): raw.rfind("}") + 1]
        data = json.loads(raw)
        data["engine"] = "gemini"
        return data
    except Exception as e:
        d = _demo_document(document_type)
        d["engine"] = f"demo (gemini fallback: {type(e).__name__})"
        return d