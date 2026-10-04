"""Task 34 -- explicit guardrails of the read-only agent (deterministic; no model is consulted, and a model can never lift a refusal).

A request that matches a rule is refused with UNSUPPORTED_REQUEST and a machine-readable code; nothing is executed and the language model never
sees the text. The rules are wording heuristics over the request: they are deliberately conservative and are NOT a security boundary -- the real
boundary is structural (a closed tool allowlist with typed arguments, read-only backends, no SQL / URL / file / shell tool exists at all).
`scan_free_text` is also applied to free-text tool arguments so that SQL or URLs cannot be smuggled through a search string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

I = re.I

IMP = r"(?:^|[.?!;,:]\s*|\b(?:please|pls|kindly|can you|could you|would you|will you|you (?:should|must|need to|have to)|i (?:want|need|would like|'d like) you to|go ahead and|now|then|just|and)\s+)"
STRONG_WRITE = r"(?:insert|delete|remove|drop|truncate|overwrite|erase|wipe|purge|alter)"
WEAK_WRITE = r"(?:update|modify|edit|write|save|store|add|create|set|change)"
WRITE_OBJECT = r"(?:records?|rows?|tables?|data|database|db|entr(?:y|ies)|dataset|schema|quarantine|measurements?|readings?|observations?)"
CHANGE_VERB = r"(?:change|set|modify|update|override|edit|raise|lower|downgrade|upgrade|escalate|mark|reclassify|re-?classify|adjust|rewrite|correct|alter|fix)"
RISK_OBJECT = r"(?:risk|status|classification|level|score|rating|threshold)"
FABRICATE_VERB = r"(?:invent|fabricate|make up|made-up|guess|pretend|imagine|fake|simulate|extrapolate|fill in|come up with|conjure|hallucinate|assume)"
FABRICATE_OBJECT = r"(?:forecasts?|predictions?|values?|data|numbers?|figures?|evidence|reports?|readings?|risk|statuses|status|scores?|measurements?|results?|sources?|quotes?|citations?)"

RULES: list[tuple[str, str, re.Pattern, str]] = [
    ("ARBITRARY_SQL", "sql",
     re.compile(r"\b(?:select\b.{1,80}\bfrom\b|insert\s+into\b|update\s+\w+\s+set\b|delete\s+from\b|drop\s+(?:table|schema|database)\b|truncate\s+table\b|alter\s+table\b|"
                r"union\s+select\b|execute[_ ]sql|run\s+(?:this\s+|a\s+|the\s+)?(?:sql|query)|raw\s+sql|sql\s+(?:query|statement|command)|psql\b|\bpg_dump\b)", I),
     "Arbitrary SQL is not available to the agent. It can only call its fixed read-only tools."),
    ("MODIFY_DATA", "write",
     re.compile(rf"\b{STRONG_WRITE}\b.{{0,40}}\b{WRITE_OBJECT}\b|{IMP}{WEAK_WRITE}\b.{{0,40}}\b{WRITE_OBJECT}\b|\b{WRITE_OBJECT}\b.{{0,25}}\b(?:to|into)\b.{{0,15}}\b(?:database|db|table)\b", I),
     "The agent is read-only: it cannot insert, update, delete or otherwise modify data."),
    ("CHANGE_RISK_STATUS", "write",
     re.compile(rf"{IMP}{CHANGE_VERB}\b.{{0,40}}\b{RISK_OBJECT}\b", I),
     "The agent cannot change a risk classification. Risk statuses come only from the deterministic risk engine."),
    ("FABRICATE", "fabrication",
     re.compile(rf"\b{FABRICATE_VERB}\b.{{0,40}}\b{FABRICATE_OBJECT}\b|\bwithout\s+(?:any\s+)?(?:data|evidence)\b.{{0,30}}\b(?:forecast|predict|say|tell)\b|"
                rf"\b(?:just\s+)?(?:make|come)\s+(?:it|something)\s+up\b", I),
     "The agent never invents facts, forecasts, evidence or values. Missing information is reported as missing."),
    ("DOCUMENTS_AS_RISK_INPUT", "provenance",
     re.compile(r"\b(?:use|treat|convert|feed|turn|count|score|include|add|put)\b.{0,50}\b(?:documents?|reports?|pdfs?|sitreps?|rag|retrieved|text|evidence|passages?|chunks?)\b"
                r".{0,60}\b(?:as|into|in|for|to)\b.{0,25}\b(?:risk (?:input|signal|score|status|model|calculation|engine)|numeric|numbers?|inputs?|signals?|a score|the score)\b", I),
     "Documents are never inputs to the risk engine or to a numeric score. Documentary evidence is shown separately."),
    ("BASELINE_AS_VALIDATED_ML", "provenance",
     re.compile(r"\b(?:call|describe|present|label|treat|market|claim|state|say|report|show|tell me)\b.{0,70}\bas\s+(?:a\s+|an\s+|the\s+)?(?:validated|proven|verified|real|trained|machine[- ]learning|ml|ai)\b|"
                r"\b(?:baseline|persistence)\b.{0,40}\b(?:is|are|counts? as|=)\s+(?:a\s+|an\s+)?(?:validated|proven|verified)\s+(?:ml|machine[- ]learning|model)", I),
     "A baseline forecast is never described as a validated ML model. Forecasts are returned with their true status (PREDICTED, BASELINE_ONLY or INSUFFICIENT_DATA)."),
    ("EXTERNAL_WEB_REQUEST", "web",
     re.compile(r"https?://|\bwww\.|\bftp://|\b(?:fetch|download|browse|scrape|crawl|curl|wget|visit|ping)\b.{0,40}\b(?:url|website|web ?site|web page|webpage|link|endpoint|internet|online|the web)\b|"
                r"\b(?:search|google|look up|look it up)\b.{0,15}\b(?:the )?(?:web|internet|online)\b", I),
     "The agent cannot make arbitrary web or HTTP requests. It uses only PORI's own read-only capabilities."),
    ("SYSTEM_ACCESS", "system",
     re.compile(r"\b(?:run|execute|exec|launch|spawn)\b.{0,25}\b(?:shell|bash|powershell|cmd|command|script|code|python|terminal|subprocess)\b|\b(?:read|open|list|cat|show|write|delete)\b.{0,25}\b(?:files?|filesystem|directory|folder|\.env|environment variables?|api keys?|secrets?|credentials?|passwords?)\b|"
                r"\brm\s+-rf\b|\bsudo\b", I),
     "The agent has no shell, file-system or credential access."),
    ("GEOGRAPHY_INFERENCE", "geography",
     re.compile(r"\b(?:which|what)\s+(?:district|province|tehsil|city|area|region)\b.{0,70}\b(?:river|gauge|gage|station|barrage|dam|canal|bridge|tehsil|taluka)\b|"
                r"\b(?:river|gauge|gage|station|barrage|dam|canal|tehsil|taluka)\b.{0,70}\b(?:belongs? to|located in|lies in|part of|falls? (?:in|under)|inside|within)\b.{0,20}\b(?:district|province)\b|"
                r"\b(?:map|assign|link|associate|match|attach|connect|guess|infer)\b.{0,40}\b(?:gauges?|gages?|stations?|rivers?|tehsils?|cities|towns?|barrages?)\b.{0,40}\b(?:to|with|onto)\b.{0,20}\b(?:districts?|provinces?|admin)", I),
     "Gauges, rivers, barrages, tehsils and towns are not mapped to districts by any authoritative mapping in this project, so the agent will not infer one."),
    ("GEOGRAPHY_LEVEL_UNSUPPORTED", "geography",
     re.compile(r"\b(?:tehsils?|talukas?|union councils?|villages?|localit(?:y|ies)|neighbou?rhoods?|mohalla|ward)\b", I),
     "Only provinces and districts are supported. Tehsil, town, union-council and locality data does not exist in the canonical geography."),
]

REFUSAL_HINT = ("Supported questions: the latest or a dated risk status of a province or district, documentary evidence from official reports, the ML/baseline "
                "forecast of AQI where one exists, province/district lookups, and combinations of these.")


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: Optional[str] = None
    category: Optional[str] = None
    message: Optional[str] = None
    matched: Optional[str] = None

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "code": self.code, "category": self.category, "message": self.message, "hint": None if self.allowed else REFUSAL_HINT}


ALLOWED = PolicyDecision(True)


def check_request(text: str) -> PolicyDecision:
    """The first matching rule refuses the request (rules are ordered most specific/dangerous first)."""
    t = " ".join((text or "").split())
    for code, category, pat, message in RULES:
        m = pat.search(t)
        if m:
            return PolicyDecision(False, code, category, message, m.group(0)[:80])
    return ALLOWED


FREE_TEXT_RULES = ("ARBITRARY_SQL", "EXTERNAL_WEB_REQUEST", "SYSTEM_ACCESS")


def scan_free_text(text: str) -> Optional[PolicyDecision]:
    """For free-text TOOL arguments (a search query, a question): reject SQL, URLs and system access smuggled inside the string."""
    t = " ".join((text or "").split())
    for code, category, pat, message in RULES:
        if code in FREE_TEXT_RULES:
            m = pat.search(t)
            if m:
                return PolicyDecision(False, code, category, message, m.group(0)[:80])
    return None
