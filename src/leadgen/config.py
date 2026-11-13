"""Layered configuration and environment settings.

Rule book layers (later wins): built-in DEFAULTS -> niche preset
(presets/<name>.yaml) -> client values (config/client.yaml).

Merge rules: dictionaries merge key by key; lists replace the earlier list,
except lists of rules that carry an "id" (forbidden claims, handover triggers,
injection patterns), which merge by id so a preset can add rules without
dropping the built-in safety ones.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ConfigError(Exception):
    """A setting or config file is missing or invalid."""


# --------------------------------------------------------------------------- rule book


class Company(BaseModel):
    name: str = "Example Co"
    city: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    about: str = ""
    services: list[str] = Field(default_factory=list)
    customers: list[str] = Field(default_factory=list)


class Tone(BaseModel):
    style: str = "Warm, clear and professional. Short sentences. No pressure."
    languages: list[str] = Field(default_factory=lambda: ["english", "roman_urdu"])
    sign_off: str = "Team"
    max_questions: int = 3  # per draft reply
    max_questions_nurture: int = 1  # per nurture draft


class WorkingHours(BaseModel):
    timezone: str = "Asia/Karachi"
    days: str = "Monday to Saturday"
    hours: str = "09:00 to 18:00"


class Question(BaseModel):
    field: str
    question: str
    question_roman_urdu: str = ""


class Band(BaseModel):
    """Points for a value that reaches `min`."""

    min: int
    points: int


class Rubric(BaseModel):
    property_type: dict[str, int] = Field(default_factory=dict)
    # Bill and load both measure "how big is the energy need": the better one counts.
    monthly_bill_pkr: list[Band] = Field(default_factory=list)
    sanctioned_load_kw: list[Band] = Field(default_factory=list)
    location: dict[str, int] = Field(default_factory=dict)
    timeline: dict[str, int] = Field(default_factory=dict)
    # A quote and a site visit both show intent: the stronger one counts.
    quote_requested: int = 0
    site_visit_requested: int = 0


class Scoring(BaseModel):
    hot_threshold: int = 7
    min_score: int = 1
    max_score: int = 10
    rubric: Rubric = Field(default_factory=Rubric)


class ServiceArea(BaseModel):
    core: list[str] = Field(default_factory=list)
    nearby: list[str] = Field(default_factory=list)


class PatternRule(BaseModel):
    id: str
    description: str = ""
    patterns: list[str] = Field(default_factory=list)


class ExtractionHints(BaseModel):
    """Regex hints used in code to fill a field the model left unknown.

    Each maps a value to patterns, e.g. property_type: {home: ["\\bkanal\\b"]}.
    """

    property_type: dict[str, list[str]] = Field(default_factory=dict)
    product_interest: dict[str, list[str]] = Field(default_factory=dict)


class LanguageRules(BaseModel):
    """How the reply language is detected from the lead's message."""

    roman_urdu_words: list[str] = Field(default_factory=list)
    min_hits: int = 2  # distinct marker words needed to call a text Roman Urdu


class Pricing(BaseModel):
    """Token prices used only for the cost ESTIMATE in the run log."""

    input_per_1m_usd: float = 0.0
    output_per_1m_usd: float = 0.0


class RuleBook(BaseModel):
    niche: str = "generic"
    company: Company = Field(default_factory=Company)
    calendar_link: str = "https://example.com/book-a-call"
    tone: Tone = Field(default_factory=Tone)
    working_hours: WorkingHours = Field(default_factory=WorkingHours)
    qualification_questions: list[Question] = Field(default_factory=list)
    scoring: Scoring = Field(default_factory=Scoring)
    service_area: ServiceArea = Field(default_factory=ServiceArea)
    handover_triggers: list[PatternRule] = Field(default_factory=list)
    forbidden_claims: list[PatternRule] = Field(default_factory=list)
    injection_patterns: list[PatternRule] = Field(default_factory=list)
    extraction_hints: ExtractionHints = Field(default_factory=ExtractionHints)
    language: LanguageRules = Field(default_factory=LanguageRules)
    contact_request_patterns: list[str] = Field(default_factory=list)
    duplicate_route: str = "handover"
    pricing: Pricing = Field(default_factory=Pricing)


# Safety rules that apply to every niche. Presets add to these; they merge by id.
DEFAULTS: dict[str, Any] = {
    "language": {
        "roman_urdu_words": [
            "hai",
            "hain",
            "kya",
            "kitna",
            "kitne",
            "kitni",
            "chahiye",
            "chahte",
            "karna",
            "karwana",
            "lagwana",
            "lagwani",
            "bijli",
            "ghar",
            "hamara",
            "hamari",
            "mera",
            "meri",
            "aap",
            "apka",
            "bhai",
            "nahi",
            "nahin",
            "mein",
            "ka",
            "ki",
            "ke",
            "ko",
            "se",
            "hoga",
            "batayen",
            "batain",
            "bata",
            "dein",
            "qeemat",
            "shukriya",
            "assalam",
            "yeh",
            "aur",
            "liye",
            "kab",
            "kahan",
            "kaise",
            "bhej",
            "taqreeban",
            "sheher",
            "tak",
        ],
        "min_hits": 2,
    },
    # A draft matching one of these asks the customer for contact details.
    "contact_request_patterns": [
        r"\b(your|best|share|provide|send|give)\b.{0,40}\b(phone|contact|mobile|whatsapp|cell)"
        r"\s*(number|no\b|details?)",
        r"\b(your|an)\s+e-?mail(\s+address)?\b[^.?!]{0,60}\?",
        r"\bbest\b.{0,25}\bto (reach|contact|call) you\b",
        r"\bhow (can|should|do) we (reach|contact) you\b",
        r"\brabta karne ke liye\b",
        r"\b(number|email)\b.{0,30}\b(bata|share kar|bhej|de dein)",
        r"\b(apna|apni|aap ka|aap ki)\b.{0,20}\b(number|email)\b",
    ],
    "handover_triggers": [
        {
            "id": "complaint",
            "description": "Complaint about service or product",
            "patterns": [
                r"\bcomplain(t|ts|ing)?\b",
                r"\brefund\b",
                r"\bnever (came|showed|called|responded|replied)\b",
                r"\b(still|is) (faulty|broken|not working)\b",
                r"\bshikayat\b",
                r"\bpaise? wapas\b",
            ],
        },
        {
            "id": "legal_threat",
            "description": "Legal threat",
            "patterns": [
                r"\blegal (action|notice)\b",
                r"\b(lawyer|advocate|attorney|court|lawsuit|adalat)\b",
                r"\bsue\b",
                r"\bcase (kar|file)",
            ],
        },
        {
            "id": "angry",
            "description": "Angry or abusive message",
            "patterns": [
                r"\b(worst|pathetic|useless|terrible|disgusting|cheat(ed|ers)?)\b",
                r"\b(fraud|scam(mers?)?|dhoka)\b",
                r"\bfed up\b",
            ],
        },
    ],
    "forbidden_claims": [
        {
            "id": "price",
            "description": "Stating or promising a price",
            "patterns": [
                r"\b(rs\.?|pkr|rupees)\s*[\d,.]+",
                r"\b[\d,.]+\s*(rs|pkr|rupees|lakh|lac|lacs|million)\b",
                r"\b(price|cost|rate) (is|will be|would be|starts)\b",
                r"\bcosts? (only|just|around|about)\b",
            ],
        },
        {
            "id": "savings",
            "description": "Promising savings or payback",
            "patterns": [
                r"\byou('ll| will| can)\b.{0,40}\bsav(e|ing|ings)\b",
                r"\b\d+\s*(%|percent)",
                r"\bzero bill\b",
                r"\bpay(s)? (for itself|back)\b",
                r"\bpayback\b",
            ],
        },
        {
            "id": "delivery_date",
            "description": "Promising a delivery or installation date",
            "patterns": [
                r"\b(within|in)\s+\d+\s+(working |business )?(day|week|month)s?\b",
                r"\b(installed|delivered|completed|ready|done) (by|within|in)\b",
                r"\bby (tomorrow|next week|next month|monday|friday)\b",
            ],
        },
        {
            "id": "guarantee",
            "description": "Guarantees of any kind",
            "patterns": [r"\bguarantee(d|s)?\b", r"\b(we|i) promise\b", r"\b100\s*%"],
        },
        {
            "id": "advice",
            "description": "Electrical, legal or tax advice",
            "patterns": [
                r"\btax (credit|deduction|exemption|rebate|benefit)s?\b",
                r"\b(legally|by law) (you|required|allowed)\b",
                r"\byou (should|can|must) (wire|rewire|connect|bypass)\b",
                r"\b(breaker|cable|wire) size\b",
            ],
        },
        {
            "id": "sent",
            "description": "Claiming something was already sent (this system only drafts)",
            "patterns": [r"\b(we|i) (have|'ve) (sent|emailed|dispatched)\b"],
        },
    ],
    "injection_patterns": [
        {
            "id": "override",
            "description": "Tries to override the agent's instructions",
            "patterns": [
                r"\b(ignore|disregard|forget)\b.{0,30}\b(instruction|rule|prompt)s?\b",
                r"\b(system|developer) (prompt|message|mode)\b",
                r"\byou are now\b",
                r"\bnew instructions?\b",
                r"\breveal\b.{0,30}\b(prompt|instructions?)\b",
                r"</?\s*lead_data",
            ],
        },
        {
            "id": "manipulate",
            "description": "Tries to dictate the score, route or an action",
            "patterns": [
                r"\b(set|give|make)\b.{0,20}\bscore\b",
                r"\bscore (me|this|it)?\s*(as|to|=|:)?\s*10\b",
                r"\bmark (me|this)( lead)? as (hot|approved)\b",
                r"\b(call|use|run) the \w+ tool\b",
                r"\bsend (an? )?(email|message|reply) to\b",
            ],
        },
    ],
}


def deep_merge(base: Any, override: Any) -> Any:
    """Merge `override` onto `base` following the rules in the module docstring."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(base[key], value) if key in base else value
        return merged
    if _is_id_list(base) and _is_id_list(override):
        by_id = {item["id"]: item for item in base}
        by_id.update({item["id"]: item for item in override})
        return list(by_id.values())
    return override


def _is_id_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, dict) and "id" in item for item in value)
    )


def project_root() -> Path:
    """The folder holding presets/, config/ and data/."""
    cwd = Path.cwd()
    if (cwd / "presets").is_dir():
        return cwd
    return Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level")
    return data


def load_rulebook(preset: str = "solar", client_config: str | Path | None = None) -> RuleBook:
    """Resolve defaults -> presets/<preset>.yaml -> client config file."""
    root = project_root()
    preset_path = root / "presets" / f"{preset}.yaml"
    if not preset_path.is_file():
        raise ConfigError(f"Preset '{preset}' not found at {preset_path}")
    data = deep_merge(DEFAULTS, _read_yaml(preset_path))
    if client_config:
        client_path = Path(client_config)
        if not client_path.is_absolute():
            client_path = root / client_path
        if client_path.is_file():  # a missing client file means "preset only"
            data = deep_merge(data, _read_yaml(client_path))
    try:
        return RuleBook.model_validate(data)
    except ValueError as exc:
        raise ConfigError(f"Invalid rule book: {exc}") from exc


# --------------------------------------------------------------------------- environment


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got '{raw}'") from exc
    if value < 1:
        raise ConfigError(f"{name} must be 1 or more, got {value}")
    return value


def _flag(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Everything read from the environment. Names and defaults match example.env."""

    openai_api_key: str = ""
    llm_provider: str = "openai"
    llm_model: str = ""
    mock_llm: bool = False
    max_leads_per_run: int = 25
    max_tool_calls_per_lead: int = 12
    max_tokens_per_run: int = 200_000
    preset: str = "solar"
    client_config: str = "config/client.yaml"
    data_dir: str = "data/runtime"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        origins = tuple(o.strip() for o in env.get("CORS_ORIGINS", "").split(",") if o.strip()) or (
            "http://localhost:5173",
        )
        return cls(
            openai_api_key=env.get("OPENAI_API_KEY", "").strip(),
            llm_provider=(env.get("LLM_PROVIDER", "").strip() or "openai").lower(),
            llm_model=env.get("LLM_MODEL", "").strip(),
            mock_llm=_flag(env, "LEADGEN_MOCK_LLM"),
            max_leads_per_run=_int(env, "MAX_LEADS_PER_RUN", 25),
            max_tool_calls_per_lead=_int(env, "MAX_TOOL_CALLS_PER_LEAD", 12),
            max_tokens_per_run=_int(env, "MAX_TOKENS_PER_RUN", 200_000),
            preset=env.get("LEADGEN_PRESET", "").strip() or "solar",
            client_config=env.get("LEADGEN_CLIENT_CONFIG", "").strip() or "config/client.yaml",
            data_dir=env.get("LEADGEN_DATA_DIR", "").strip() or "data/runtime",
            api_host=env.get("API_HOST", "").strip() or "127.0.0.1",
            api_port=_int(env, "API_PORT", 8000),
            cors_origins=origins,
        )

    def resolved_data_dir(self) -> Path:
        path = Path(self.data_dir)
        return path if path.is_absolute() else project_root() / path
