"""Exercise production inquiry services with isolated data and scripted providers.

This measures workflow contracts, including negative paths. It does not measure
semantic retrieval, live LLM correctness, PostgreSQL concurrency, or actual n8n.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import re
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ai.base import LLMMessage, LLMResponse
from app.ai.providers.mock_provider import MockLLMProvider
from app.core.exceptions import ValidationException
from app.db.base import Base
from app.db.models import Message, Product  # also registers application models
from app.db.models.enums import Channel, LeadStatus, MessageStatus
from app.db.models.lead import Lead
from app.rag.base import RetrievalChunk, RetrievalResult, Retriever
from app.schemas.inquiry import CustomerIntake, InquiryRequest
from app.services.inquiry_service import InquiryService
from app.services.rag_service import RAGService


class FixtureRetriever(Retriever):
    """Simple keyword fixture selector; intentionally not production vector retrieval."""

    def __init__(self, chunks: list[RetrievalChunk]):
        self.chunks = chunks

    async def search(self, query: str, top_k: int = 4, filters=None, threshold=None):
        terms = set(re.findall(r"\w+", query.casefold())) - {
            "what",
            "which",
            "does",
            "the",
            "for",
            "are",
            "how",
            "long",
            "is",
            "a",
            "do",
            "you",
        }
        matches = [
            c
            for c in self.chunks
            if len(terms & set(re.findall(r"\w+", c.content.casefold()))) >= 2
        ]
        return RetrievalResult(query=query, chunks=matches[:top_k], total_found=len(matches))


class ScriptedProvider(MockLLMProvider):
    """Fixed fixture answer or controlled provider failure; no network calls."""

    def __init__(self, reply: str, fail: bool = False):
        super().__init__(default_reply=reply)
        self.fail = fail

    async def generate(self, messages: list[LLMMessage | dict], **kwargs) -> LLMResponse:
        if self.fail:
            raise RuntimeError("Controlled evaluation provider failure")
        return await super().generate(messages, **kwargs)


class FailingSender:
    async def send_customer_reply(self, customer_phone: str, text: str):
        raise RuntimeError("Controlled evaluation send failure")


def load_dataset(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or Path(__file__).with_name("cases.json")).read_text())


async def evaluate_case(business: dict, scenario: str) -> dict:
    start = time.perf_counter()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    result = {
        "case_id": f"{business['id']}/{scenario}",
        "business": business["name"],
        "scenario": scenario,
        "checks": {},
        "error": None,
    }
    try:
        with Session(engine, expire_on_commit=False) as db:
            db.add(
                Product(
                    sku=business["sku"],
                    slug=business["id"],
                    name=business["product"],
                    category="Evaluation",
                    base_price=Decimal(business["price"]),
                    currency=business["currency"],
                    lead_time_days=business["lead_time_days"],
                )
            )
            db.commit()
            chunk = RetrievalChunk(
                id=f"chunk-{business['id']}",
                document_id=f"document-{business['id']}",
                content=business["fact"],
                title=business["product"],
                source_name=business["name"],
                score=1.0,
            )
            provider = ScriptedProvider(business["reply"], fail=scenario == "provider_failure")
            retriever = FixtureRetriever([chunk])
            rag = RAGService(
                db=db,
                retriever=retriever,
                llm_provider=provider,
                business_name=business["name"],
                business_description=business["description"],
            )
            question = (
                "Do you sell aircraft insurance?"
                if scenario == "unsupported"
                else business["question"]
            )
            inquiry = await InquiryService.process_inquiry(
                db,
                InquiryRequest(
                    customer=CustomerIntake(first_name="Synthetic", phone="+15550000001"),
                    channel=Channel.WHATSAPP,
                    message=question,
                    preferred_product_skus=[] if scenario == "unsupported" else [business["sku"]],
                ),
                llm_provider=provider,
                rag_service=rag,
            )
            checks = result["checks"]
            checks["no_send_before_approval"] = (
                not inquiry.outbound_message_sent
                and not db.scalars(
                    select(Message).where(Message.status == MessageStatus.SENT.value)
                ).all()
            )
            result["workflow_status"] = inquiry.status
            result["answer"] = inquiry.draft.content if inquiry.draft else None
            result["sources"] = (
                [s.model_dump(mode="json") for s in inquiry.draft.evidence_sources]
                if inquiry.draft
                else []
            )
            if scenario == "provider_failure":
                checks["provider_failure_is_visible"] = inquiry.status == "FAILED" and bool(
                    inquiry.error
                )
                checks["failed_workflow_has_no_draft"] = inquiry.draft is None
            else:
                checks["lead_created"] = bool(inquiry.lead_id)
                loaded = InquiryService.get_inquiry_status(db, inquiry.workflow_run_id)
                checks["citations_survive_reload"] = bool(loaded.draft) and (
                    [s.model_dump() for s in loaded.draft.evidence_sources]
                    == [s.model_dump() for s in inquiry.draft.evidence_sources]
                )
                if scenario == "unsupported":
                    checks["unsupported_inquiry_needs_review"] = (
                        inquiry.status == "NEEDS_REVIEW" and not inquiry.draft.grounded
                    )
                    checks["unsupported_has_no_sources"] = not inquiry.draft.evidence_sources
                    rejected = InquiryService.reject_inquiry(
                        db, inquiry.workflow_run_id, reason="No evidence"
                    )
                    checks["rejection_does_not_send"] = not rejected.outbound_message_sent
                    try:
                        await InquiryService.approve_inquiry(db, inquiry.workflow_run_id)
                    except ValidationException:
                        checks["rejected_draft_cannot_be_approved"] = True
                    else:
                        checks["rejected_draft_cannot_be_approved"] = False
                else:
                    checks["expected_source_returned"] = any(
                        s.document_id == chunk.document_id for s in loaded.draft.evidence_sources
                    )
                    prompt = provider.history[-1][0].content
                    checks["business_context_used"] = business["name"] in prompt
                    checks["catalog_values_preserved"] = (
                        f"{business['currency']} {business['price']}" in prompt
                        and f"{business['lead_time_days']} days" in prompt
                    )
                    approved = await InquiryService.approve_inquiry(
                        db,
                        inquiry.workflow_run_id,
                        whatsapp_service=FailingSender()
                        if scenario == "delivery_failure"
                        else None,
                    )
                    msg = db.get(Message, approved.draft.message_id)
                    lead = db.get(Lead, approved.lead_id)
                    if scenario == "delivery_failure":
                        checks["send_failure_not_reported_as_sent"] = (
                            not approved.outbound_message_sent and msg.sent_at is None
                        )
                        checks["send_failure_is_visible"] = (
                            approved.delivery_status == "FAILED" and bool(approved.delivery_error)
                        )
                        checks["failed_send_does_not_contact_lead"] = (
                            lead.status == LeadStatus.NEW.value
                        )
                    else:
                        checks["approved_mock_send_recorded"] = (
                            approved.outbound_message_sent
                            and approved.delivery_status == "SENT"
                            and bool(msg.external_message_id)
                        )
                        checks["successful_send_contacts_lead"] = (
                            lead.status == LeadStatus.CONTACTED.value
                        )
                    try:
                        await InquiryService.approve_inquiry(db, inquiry.workflow_run_id)
                    except ValidationException:
                        checks["repeated_approval_blocked"] = True
                    else:
                        checks["repeated_approval_blocked"] = False
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        engine.dispose()
    result["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
    result["passed"] = (
        bool(result["checks"]) and all(result["checks"].values()) and result["error"] is None
    )
    return result


async def run_evaluation(dataset: dict | None = None) -> dict:
    dataset = dataset or load_dataset()
    results = [
        await evaluate_case(business, scenario)
        for business in dataset["businesses"]
        for scenario in dataset["scenarios"]
    ]
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        revision = None
        dirty = None
    metrics = {}
    for name in sorted({name for r in results for name in r["checks"]}):
        values = [r["checks"][name] for r in results if name in r["checks"]]
        metrics[name] = {"passed": sum(values), "total": len(values)}
    return {
        "mode": "offline_contract_evaluation",
        "timestamp": datetime.now(UTC).isoformat(),
        "revision": revision,
        "working_tree_dirty": dirty,
        "dataset_sha256": hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest(),
        "python": platform.python_version(),
        "providers": {
            "llm": "scripted fixture",
            "retrieval": "keyword fixture",
            "messaging": "mock",
            "database": "isolated SQLite",
        },
        "limitations": [
            "Not an LLM factuality benchmark",
            "Does not exercise pgvector or PostgreSQL row locks",
            "Does not run n8n or external messaging",
            "Local timings include setup and are not production latency",
        ],
        "summary": {"passed": sum(r["passed"] for r in results), "total": len(results)},
        "metrics": metrics,
        "cases": results,
    }


def render_report(report: dict) -> str:
    lines = [
        "# CraftFlow offline contract evaluation",
        "",
        f"Cases passed: {report['summary']['passed']}/{report['summary']['total']}",
        "",
        "Scripted generation and keyword retrieval fixtures exercise production inquiry services. Results measure workflow contracts, not AI quality or live n8n delivery.",
        "",
        "| Check | Passed | Total |",
        "|---|---:|---:|",
    ]
    lines.extend(
        f"| {name} | {m['passed']} | {m['total']} |" for name, m in report["metrics"].items()
    )
    lines.extend(
        [
            "",
            "Limitations:",
            *[f"- {line}" for line in report["limitations"]],
            "",
            "See the JSON report for raw case outcomes, answers, citations, and errors.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/evaluation"))
    args = parser.parse_args()
    report = asyncio.run(run_evaluation())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output / "report.md").write_text(render_report(report))
    print(
        f"Offline workflow cases: {report['summary']['passed']}/{report['summary']['total']} passed"
    )
    print(f"Reports: {args.output.resolve()}")
    raise SystemExit(
        0
        if report["summary"]["passed"] == report["summary"]["total"] and report["summary"]["total"]
        else 1
    )


if __name__ == "__main__":
    main()
