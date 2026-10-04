"""Task 34 test doubles: in-memory tool backends (no database, no network, no credential) and a scripted language-model provider.
They exercise the agent's orchestration, validation and provenance handling -- not the quality of a real model."""

from __future__ import annotations

from datetime import datetime, timezone

from pipeline.agents import geography as agent_geo
from pipeline.agents.contracts import TOOL_EMPTY, TOOL_OK
from pipeline.agents.executor import ToolExecutor
from pipeline.agents.orchestrator import AgentDeps
from pipeline.rag.llm import LLMMalformedResponse, LLMResult, LLMUnavailable

UNITS = [{"id": 2, "level": 1, "name": "Punjab", "province": None}, {"id": 3, "level": 1, "name": "Sindh", "province": None},
         {"id": 8, "level": 1, "name": "Islamabad Capital Territory", "province": None}, {"id": 9, "level": 1, "name": "Khyber Pakhtunkhwa", "province": None},
         {"id": 30, "level": 2, "name": "Lahore", "province": "Punjab"}, {"id": 46, "level": 2, "name": "Sialkot", "province": "Punjab"},
         {"id": 50, "level": 2, "name": "Swat", "province": "Khyber Pakhtunkhwa"}, {"id": 62, "level": 2, "name": "Islamabad", "province": "Islamabad Capital Territory"}]
BY_ID = {u["id"]: u for u in UNITS}


def risk_row(uid, name, status, d, level=2, province="Punjab"):
    return {"admin_unit_id": uid, "admin_unit_name": name, "admin_level": level, "province": province, "risk_date": d, "risk_status": status,
            "risk_basis": "THRESHOLD_BASED", "risk_score": None, "risk_confidence": "MEDIUM",
            "signals": {"rainfall": None, "weather": None, "gauge": None, "air_quality": None, "hazard_alert": None, "disaster_event": None},
            "active_signal_count": 1, "observed_signal_count": 1, "missing_signal_count": 5, "top_risk_domain": None, "top_risk_contribution": None,
            "data_coverage_pct": 16.67, "source_count": 1, "source_record_count": 1, "calculation_version": "risk-engine-1.0.0", "threshold_status": "PROVISIONAL"}


RISK = [risk_row(30, "Lahore", "LOW", "2026-09-15"), risk_row(30, "Lahore", "HIGH", "2026-07-01"), risk_row(46, "Sialkot", "MODERATE", "2026-07-11")]


def ml_row(status, h=1, model_type="baseline", prediction=126.0, reason=None, uid=30):
    return {"model_run_id": f"air_quality_index-h{h}-abc", "entity_type": "admin_unit", "entity_id": str(uid), "admin_unit_id": uid, "horizon_days": h,
            "prediction_date": "2026-09-16", "feature_cutoff": "2026-09-15", "target": "air_quality_index", "unit": "AQI", "prediction": prediction, "status": status,
            "reason": reason, "model_name": "persistence" if model_type == "baseline" else "ridge", "model_version": "1.0.0+abc", "model_type": model_type,
            "training_cutoff": "2026-07-26", "provenance": {"provenance": "ML_MODEL", "validated_against_baseline": status == "PREDICTED"}}


ML = {30: [ml_row("BASELINE_ONLY", 1), ml_row("BASELINE_ONLY", 3, prediction=135.4), ml_row("BASELINE_ONLY", 7, prediction=135.4)],
      46: [ml_row("INSUFFICIENT_DATA", 1, "none", None, "no air_quality observations exist for this area", 46)]}


def evidence(cid="ndma:sitrep:a#c0001", text="NDMA reported flooding in Sindh."):
    return {"document_id": cid.split("#")[0], "chunk_id": cid, "title": "NDMA Sitrep 12", "source": "ndma", "source_type": "sitrep", "document_date": "2026-07-05",
            "geography": {}, "event": {}, "snippet": text, "text": text, "relevance": {"score": 0.03, "method": "bm25"}, "source_reference": {"url": None, "file_path": "x", "content_sha256": "0" * 64}}


class Backends:
    """A call-logging set of backends. `docs` = evidence chunks returned by rag.retrieve (a callable may inspect the arguments)."""

    def __init__(self, docs=None, risk=None, ml=None, units=None, intel_body=None):
        self.docs = [evidence()] if docs is None else docs
        self.risk = RISK if risk is None else risk
        self.ml = ML if ml is None else ml
        self.units = UNITS if units is None else units
        self.intel_body = intel_body
        self.calls = []

    def _log(self, name, args):
        self.calls.append((name, dict(args)))

    def resolve_place(self, a):
        self._log("geography.resolve_place", a)
        return {"status": TOOL_OK, "result": agent_geo.resolve_place(a["text"], self.units)}

    def get_admin_unit(self, a):
        self._log("geography.get_admin_unit", a)
        u = next((x for x in self.units if x["id"] == a["admin_unit_id"]), None)
        if not u:
            return {"status": TOOL_EMPTY, "reason": "not a province or district"}
        return {"status": TOOL_OK, "result": {"status": "resolved", "unit": {"id": u["id"], "name": u["name"], "level": u["level"], "parent_id": 2 if u["province"] == "Punjab" else None,
                                                                         "province": u["province"] or u["name"], "has_geometry": True, "boundary_source": "COD-AB"}}}

    def list_units(self, a):
        self._log("geography.list_units", a)
        rows = [u for u in self.units if (a.get("level") is None or u["level"] == a["level"]) and (not a.get("province") or u["province"] == a["province"])]
        return {"status": TOOL_OK if rows else TOOL_EMPTY, "result": {"count": len(rows), "units": rows}}

    def _risk(self, uid, d=None):
        rows = sorted((r for r in self.risk if r["admin_unit_id"] == uid and (d is None or r["risk_date"] == d)), key=lambda r: r["risk_date"], reverse=True)
        return rows

    def risk_latest(self, a):
        self._log("risk.latest", a)
        rows = self._risk(a["admin_unit_id"])
        return {"status": TOOL_OK if rows else TOOL_EMPTY, "result": {"record": rows[0] if rows else None, "lookup": {"basis": "latest", "admin_unit_id": a["admin_unit_id"]},
                                                                  "reason": None if rows else "no risk record exists for this area"}}

    def risk_on_date(self, a):
        self._log("risk.on_date", a)
        rows = self._risk(a["admin_unit_id"], a["date"])
        return {"status": TOOL_OK if rows else TOOL_EMPTY, "result": {"record": rows[0] if rows else None, "lookup": {"basis": "date", "date": a["date"], "admin_unit_id": a["admin_unit_id"]},
                                                                  "reason": None if rows else f"no risk record exists for this area on {a['date']}"}}

    def risk_history(self, a):
        self._log("risk.history", a)
        rows = [r for r in self._risk(a["admin_unit_id"]) if (not a.get("date_from") or r["risk_date"] >= a["date_from"]) and (not a.get("date_to") or r["risk_date"] <= a["date_to"])]
        return {"status": TOOL_OK if rows else TOOL_EMPTY, "result": {"records": rows, "lookup": {"basis": "window"}, "reason": None if rows else "no risk record in the window"}}

    def risk_coverage(self, a):
        self._log("risk.coverage", a)
        rows = self._risk(a["admin_unit_id"])
        return {"status": TOOL_OK if rows else TOOL_EMPTY, "result": {"record": rows[0] if rows else None, "coverage": {"data_coverage_pct": 16.67} if rows else None, "lookup": {}}}

    def rag_retrieve(self, a):
        self._log("rag.retrieve", a)
        docs = self.docs(a) if callable(self.docs) else self.docs
        items = [{"chunk_id": d["chunk_id"], "text": d["text"]} for d in docs]
        return {"status": TOOL_OK if docs else TOOL_EMPTY, "result": {"records": docs, "items": items, "retrieval": {"mode": a.get("mode", "hybrid"), "method": "fake", "min_score": None, "embedding_model": None}}}

    def ml_predictions(self, a):
        self._log("ml.predictions", a)
        rows = [r for r in self.ml.get(a["admin_unit_id"], []) if not a.get("horizon") or r["horizon_days"] == a["horizon"]]
        res = {"predictions": rows}
        if a.get("horizon") and not rows:
            res["available_horizons"] = sorted({r["horizon_days"] for r in self.ml.get(a["admin_unit_id"], [])})
        return {"status": TOOL_OK if rows else TOOL_EMPTY, "result": res}

    def ml_models(self, a):
        self._log("ml.models", a)
        return {"status": TOOL_OK, "result": {"models": [{"target": "air_quality_index", "horizon_days": 1, "model_type": "baseline", "status": "BASELINE_ONLY"}]}}

    def intelligence_ask(self, a):
        self._log("intelligence.ask", a)
        return {"status": TOOL_OK, "result": self.intel_body}

    def mapping(self):
        return {"geography.resolve_place": self.resolve_place, "geography.get_admin_unit": self.get_admin_unit, "geography.list_units": self.list_units,
                "risk.latest": self.risk_latest, "risk.on_date": self.risk_on_date, "risk.history": self.risk_history, "risk.coverage": self.risk_coverage,
                "rag.retrieve": self.rag_retrieve, "ml.predictions": self.ml_predictions, "ml.models": self.ml_models, "intelligence.ask": self.intelligence_ask}

    def names(self):
        return [n for n, _ in self.calls]


class Scripted:
    """A scripted stand-in for a language model. `texts` are returned in order; the last one repeats. NOT a model."""
    name, model = "scripted", "s-1"

    def __init__(self, *texts):
        self.texts, self.calls = list(texts), []

    def generate(self, system, question, evidence, constraints):
        self.calls.append({"system": system, "question": question, "evidence": evidence})
        t = self.texts[min(len(self.calls) - 1, len(self.texts) - 1)]
        if isinstance(t, Exception):
            raise t
        return LLMResult(t, self.name, self.model)


def no_provider():
    raise LLMUnavailable("no LLM provider is configured")


def deps(backends: Backends, provider=None, now=None):
    def factory():
        if provider is None:
            raise LLMUnavailable("no LLM provider is configured")
        return provider
    clock = now or (lambda: datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc))
    return AgentDeps(executor=ToolExecutor(backends.mapping(), clock=lambda: 0.0), provider_factory=factory, now=clock)
