"""Pydantic models shared across the app."""
from typing import Optional, List, Literal
from pydantic import BaseModel

Level = Literal["low", "medium", "high"]
Verdict = Literal["consistent", "attention", "inconsistent"]


class OnboardingIn(BaseModel):
    name: str
    cnic: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    employment_type: Optional[str] = None
    business_type: Optional[str] = None
    monthly_income: float = 0
    account_purpose: Optional[str] = None
    expected_monthly_transactions: float = 0


class Signal(BaseModel):
    label: str
    value: str
    verdict: Verdict
    note: str


class RiskResult(BaseModel):
    level: Level
    confidence: int
    signals: List[Signal]
    conclusion: str
    engine: str


class OfficerAction(BaseModel):
    action: Literal["approve", "request_clarification", "escalate", "reject"]
    note: Optional[str] = None
    officer: str = "officer"


class Clarification(BaseModel):
    message: str