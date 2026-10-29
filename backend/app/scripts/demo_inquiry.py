"""Reproducible demo script for the end-to-end customer inquiry workflow using mock providers.

Can be run via:
    python -m app.scripts.demo_inquiry
or
    python backend/app/scripts/demo_inquiry.py
"""

# ruff: noqa: E402
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parents[2]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.base import LLMMessage, LLMProvider, LLMResponse
from app.db.base import Base
from app.db.models.enums import ActorType, Channel, CustomerSource, ProductAvailability
from app.db.models.product import Product, ProductVariant
from app.rag.base import RetrievalChunk, RetrievalResult, Retriever
from app.schemas.inquiry import CustomerIntake, InquiryRequest
from app.services.inquiry_service import InquiryService
from app.services.rag_service import RAGService


class DemoRetriever(Retriever):
    """In-memory demo retriever returning verified sample knowledge chunks."""

    def __init__(self, chunks: list[RetrievalChunk]):
        self.chunks = chunks

    async def search(
        self,
        query: str,
        top_k: int = 4,
        filters: dict | None = None,
        threshold: float | None = None,
    ) -> RetrievalResult:
        stopwords = {
            "and",
            "the",
            "for",
            "with",
            "from",
            "you",
            "are",
            "our",
            "what",
            "how",
            "can",
            "do",
            "your",
        }
        terms = [
            t.strip("?,.!")
            for t in query.lower().split()
            if len(t.strip("?,.!")) > 3 and t.strip("?,.!") not in stopwords
        ]
        matched = []
        for c in self.chunks:
            haystack = f"{c.title} {c.content} {c.source_name}".lower()
            matching_terms = [t for t in terms if t in haystack]
            if matching_terms:
                c.score = min(0.95, 0.4 + (len(matching_terms) * 0.15))
                matched.append(c)

        matched.sort(key=lambda x: x.score or 0.0, reverse=True)
        return RetrievalResult(
            query=query,
            chunks=matched[:top_k],
            total_found=len(matched),
        )


class DemoLLMProvider(LLMProvider):
    """Context-aware mock provider for demo scenarios."""

    async def generate(self, messages: list[LLMMessage | dict], **kwargs) -> LLMResponse:
        full_text = " ".join(
            (m.content if hasattr(m, "content") else str(m.get("content", ""))) for m in messages
        ).lower()

        if "aircraft" in full_text or "hangar" in full_text or "jet" in full_text:
            reply = (
                "The available business knowledge does not contain enough information "
                "to answer this question. Our team will review your inquiry and follow up shortly."
            )
        else:
            reply = (
                "Thank you for contacting us regarding our luxury stone bathtubs! "
                "Our Lotus Freestanding Bathtub is hand-carved from monolithic Carrara marble, "
                "starting at $12,500 with an 8 to 12 week production lead time. "
                "We offer both Honed Matte and High Polish finishes, and full dimensional customization. "
                "A 50% deposit reserves your quarry block. Our design specialist will follow up with full details."
            )

        return LLMResponse(
            content=reply,
            model="mock-gpt-model",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


class FailingLLMProvider(LLMProvider):
    """Simulated provider that fails during generation."""

    async def generate(self, messages: list[LLMMessage | dict], **kwargs) -> LLMResponse:
        raise RuntimeError("Simulated AI Provider connection timeout / API 500 error")

    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


def setup_demo_db() -> Session:
    """Create an isolated in-memory SQLite database pre-seeded with sample catalog items."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    # Seed sample products
    prod1 = Product(
        sku="LOTUS-001",
        name="Lotus Freestanding Bathtub",
        slug="lotus-freestanding-bathtub",
        material="Carrara Marble",
        category="Bathtubs",
        base_price=Decimal("12500.00"),
        lead_time_days=70,
        availability_status=ProductAvailability.MADE_TO_ORDER.value,
        description="Sculpted from a single monolithic block of Italian Bianco Carrara marble.",
    )
    session.add(prod1)
    session.flush()

    var1 = ProductVariant(
        product_id=prod1.id,
        sku_suffix="HONED",
        name="Honed Matte Finish",
        price_adjustment=Decimal("0.00"),
    )
    var2 = ProductVariant(
        product_id=prod1.id,
        sku_suffix="POL",
        name="High Polish Finish",
        price_adjustment=Decimal("850.00"),
    )
    session.add_all([var1, var2])

    prod2 = Product(
        sku="VERONA-002",
        name="Verona Fluted Stone Basin",
        slug="verona-fluted-stone-basin",
        material="Travertine",
        category="Basins",
        base_price=Decimal("3800.00"),
        lead_time_days=42,
        availability_status=ProductAvailability.IN_STOCK.value,
        description="Hand-fluted natural beige travertine vessel sink.",
    )
    session.add(prod2)
    session.commit()
    return session


async def run_demo():
    print("=" * 80)
    print("  CraftFlow End-to-End Inquiry Workflow Demo (Mock Providers)")
    print("=" * 80)

    db = setup_demo_db()

    # Pre-configured verified knowledge chunks for the demo
    sample_chunks = [
        RetrievalChunk(
            id="chunk-lead-time-001",
            document_id="doc-faq-001",
            source_id="src-ages-art-faq",
            source_name="Ages Art FAQ & Policies",
            title="Production Lead Times & Logistics",
            content=(
                "Standard catalog bathtubs have a production lead time of 8 to 12 weeks. "
                "Each bathtub is carved from a monolithic marble block and hand-finished. "
                "Air freight requires 7 to 10 days; ocean freight takes 4 to 6 weeks."
            ),
            score=0.92,
            chunk_index=1,
            metadata={"category": "FAQ", "topic": "lead_times"},
        ),
        RetrievalChunk(
            id="chunk-materials-002",
            document_id="doc-guide-002",
            source_id="src-ages-art-guides",
            source_name="Ages Art Material Selection Guide",
            title="Marble Sourcing and Customization",
            content=(
                "We offer premium Bianco Carrara, Calacatta Viola, Nero Marquina, and Silver Travertine. "
                "All bathtubs are customizable in dimensions, drain positioning, and finish (honed matte or high polish). "
                "A 50% deposit confirms quarry block reservation and CAD shop drawings."
            ),
            score=0.88,
            chunk_index=2,
            metadata={"category": "Guide", "topic": "materials"},
        ),
    ]

    retriever = DemoRetriever(chunks=sample_chunks)
    mock_llm = DemoLLMProvider()
    rag_service = RAGService(db=db, retriever=retriever, llm_provider=mock_llm)

    # -------------------------------------------------------------------------
    # SCENARIO 1: Successful Inquiry with Grounded Draft and Human Approval Gate
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print(">>> SCENARIO 1: Processing a Valid Customer Inquiry")
    print("-" * 80)

    inquiry_req = InquiryRequest(
        customer=CustomerIntake(
            first_name="Eleanor",
            last_name="Vance",
            email="eleanor.vance@luxuryinteriors.com",
            phone="+1 415 555 7890",
            company_name="Vance Design Group",
            source=CustomerSource.WEBSITE,
        ),
        channel=Channel.WEBSITE,
        message=(
            "Hi, I'm designing a master bathroom in Pacific Heights and looking for a freestanding "
            "marble bathtub. What are your lead times, finishes, and pricing for Carrara marble?"
        ),
        preferred_product_skus=["LOTUS-001"],
    )

    print(f"Customer: {inquiry_req.customer.first_name} {inquiry_req.customer.last_name}")
    print(f'Inquiry Message: "{inquiry_req.message}"')
    print("\nExecuting workflow pipeline...")

    res1 = await InquiryService.process_inquiry(
        db=db,
        request=inquiry_req,
        actor_id="demo_sales_agent",
        actor_type=ActorType.AI_AGENT,
        llm_provider=mock_llm,
        rag_service=rag_service,
    )

    print(f"\nWorkflow Run ID : {res1.workflow_run_id}")
    print(f"Overall Status  : {res1.status}")
    print(f"Customer ID     : {res1.customer_id}")
    print(f"Conversation ID : {res1.conversation_id}")
    print(f"Lead ID Created : {res1.lead_id}")

    print("\nStep Diagnostics:")
    for step in res1.steps:
        status_marker = "[OK]" if step.status == "COMPLETED" else f"[{step.status}]"
        print(f"  {status_marker:<16} Step: {step.step_name:<22} Details: {step.details}")

    print("\nDraft Response (Awaiting Human Approval):")
    print(f"  Grounded: {res1.draft.grounded}")
    print(f"  Approval Status: {res1.draft.approval_status}")
    print(
        f"  Outbound Message Dispatched: {res1.outbound_message_sent} (MUST be False prior to human review)"
    )
    print(f'\n  Draft Content:\n  "{res1.draft.content}"')

    print("\nEvidence Sources Cited:")
    for cite in res1.draft.evidence_sources:
        if cite.type == "knowledge":
            print(f"  - [Knowledge] {cite.title} ({cite.source_name}) - Score: {cite.score:.2f}")
        elif cite.type == "catalog":
            print(
                f"  - [Catalog] {cite.product_name} (SKU: {cite.sku}) | Base Price: ${cite.price} | Lead Time: {cite.lead_time_days} days"
            )

    # Verify Human Approval Gate
    print("\n" + "." * 60)
    print(">>> Human Reviewer Action: Approving Outbound Response")
    print("." * 60)
    approved_res = await InquiryService.approve_inquiry(
        db=db,
        workflow_run_id=res1.workflow_run_id,
        edited_content=(
            res1.draft.content + " [Reviewed and signed off by Senior Design Consultant]"
        ),
        actor_id="human_agent_sarah",
        actor_type=ActorType.HUMAN,
    )
    print(f"Approval Result : {approved_res.draft.approval_status}")
    print(f"Outbound Sent   : {approved_res.outbound_message_sent} (Now True)")
    print(f"Approved By     : {approved_res.draft.approved_by}")
    print(f'Final Content   :\n  "{approved_res.draft.content}"')

    # -------------------------------------------------------------------------
    # SCENARIO 2: Unsupported Question (Missing Knowledge / Out of Scope)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print(">>> SCENARIO 2: Unsupported Inquiry with Zero Knowledge Matches")
    print("-" * 80)

    unsupported_req = InquiryRequest(
        customer=CustomerIntake(
            first_name="Marcus",
            last_name="Flynn",
            email="marcus.flynn@aerologistics.com",
            phone="+1 212 555 4321",
            source=CustomerSource.WEBSITE,
        ),
        channel=Channel.WEBSITE,
        message="Do you provide commercial aircraft hangar structural reinforcement and jet engine maintenance?",
    )

    print(f'Inquiry Message: "{unsupported_req.message}"')
    print("\nExecuting workflow pipeline...")

    res2 = await InquiryService.process_inquiry(
        db=db,
        request=unsupported_req,
        actor_id="demo_sales_agent",
        actor_type=ActorType.AI_AGENT,
        llm_provider=mock_llm,
        rag_service=rag_service,
    )

    print(f"\nWorkflow Run ID : {res2.workflow_run_id}")
    print(f"Overall Status  : {res2.status} (Clear state: NEEDS_REVIEW, zero hallucinations)")
    print(f"Draft Grounded  : {res2.draft.grounded} (False)")
    print(f"Lead Created    : {res2.lead_id} (Preserved in CRM for human evaluation)")
    print(f'\nDraft Content:\n  "{res2.draft.content}"')
    print(f"Outbound Sent   : {res2.outbound_message_sent} (False)")

    for step in res2.steps:
        status_marker = f"[{step.status}]"
        print(f"  {status_marker:<22} Step: {step.step_name:<22} Details: {step.details}")

    # -------------------------------------------------------------------------
    # SCENARIO 3: Provider Failure Handling (Transparent Error Diagnostics)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print(">>> SCENARIO 3: Simulating AI Provider Failure")
    print("-" * 80)

    failing_llm = FailingLLMProvider()
    failing_rag = RAGService(db=db, retriever=retriever, llm_provider=failing_llm)

    failing_req = InquiryRequest(
        customer=CustomerIntake(
            first_name="Claire",
            last_name="Underwood",
            email="claire@example.com",
            phone="+1 202 555 9999",
        ),
        channel=Channel.WEBSITE,
        message="I'd like to check bathtub prices and availability.",
    )

    print(f'Inquiry Message: "{failing_req.message}"')
    print("\nExecuting workflow with failing provider...")

    res3 = await InquiryService.process_inquiry(
        db=db,
        request=failing_req,
        actor_id="demo_sales_agent",
        actor_type=ActorType.AI_AGENT,
        llm_provider=failing_llm,
        rag_service=failing_rag,
    )

    print(f"\nWorkflow Run ID : {res3.workflow_run_id}")
    print(f"Overall Status  : {res3.status} (FAILED)")
    print(f"Error Diagnostic: {res3.error}")
    print(f"Outbound Sent   : {res3.outbound_message_sent} (Zero messages sent on failure)")

    for step in res3.steps:
        status_marker = f"[{step.status}]"
        err_info = f" Error: {step.error}" if step.error else ""
        print(f"  {status_marker:<16} Step: {step.step_name:<22}{err_info}")

    print("\n" + "=" * 80)
    print("  Demo Run Completed Successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_demo())
