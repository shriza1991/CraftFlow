"""Unit and domain model tests for P1 business entities and services."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.exceptions import ValidationException
from app.db.models import (
    ActorType,
    AgentRun,
    AgentRunStatus,
    Channel,
    Conversation,
    ConversationStatus,
    CustomerSource,
    FollowUpStatus,
    LeadPriority,
    LeadStatus,
    MessageDirection,
    MessageType,
    ProductAvailability,
    SenderType,
    ToolCall,
    ToolCallStatus,
)
from app.schemas.customer import CustomerCreate
from app.schemas.follow_up import FollowUpCreate, FollowUpUpdate
from app.schemas.lead import LeadCreate, LeadProductCreate, LeadUpdate
from app.schemas.message import MessageCreate
from app.schemas.pagination import PageParams
from app.schemas.product import ProductCreate, ProductVariantCreate
from app.services.audit_service import AuditService
from app.services.customer_service import CustomerService
from app.services.follow_up_service import FollowUpService
from app.services.lead_service import LeadService
from app.services.message_service import MessageService
from app.services.product_service import ProductService
from sqlalchemy import inspect
from sqlalchemy.orm import Session


def test_database_connection_and_tables_exist(db_session: Session):
    """Verify that PostgreSQL connection is alive and all 11 P1 domain tables exist."""
    inspector = inspect(db_session.connection())
    tables = inspector.get_table_names()

    expected_tables = [
        "products",
        "product_variants",
        "customers",
        "leads",
        "lead_products",
        "conversations",
        "messages",
        "follow_ups",
        "agent_runs",
        "tool_calls",
        "audit_logs",
    ]
    for table in expected_tables:
        assert table in tables, f"Expected table '{table}' not found in database"


def test_create_product_and_variant(db_session: Session):
    """Verify product and product variant creation and relationship."""
    unique_suffix = uuid.uuid4().hex[:6]
    product_in = ProductCreate(
        sku=f"TUB-TEST-{unique_suffix}",
        name=f"Test Marble Tub {unique_suffix}",
        slug=f"test-marble-tub-{unique_suffix}",
        material="Carrara Marble",
        category="freestanding",
        base_price=Decimal("125000.00"),
        currency="INR",
        length=Decimal("180.00"),
        width=Decimal("80.00"),
        height=Decimal("60.00"),
        weight=Decimal("380.00"),
        lead_time_days=28,
        availability_status=ProductAvailability.MADE_TO_ORDER,
        is_active=True,
        variants=[
            ProductVariantCreate(
                name="Honed Matte 72-inch",
                sku_suffix="HM-72",
                length=Decimal("182.88"),
                material="Carrara Marble",
                finish="Honed Matte",
                color="Classic White",
                price_adjustment=Decimal("15000.00"),
            )
        ],
    )
    product = ProductService.create_product(db=db_session, product_in=product_in)

    assert product.id is not None
    assert len(product.variants) == 1
    assert product.variants[0].name == "Honed Matte 72-inch"
    assert product.variants[0].price_adjustment == Decimal("15000.00")


def test_product_unique_sku_constraint(db_session: Session):
    """Verify that creating two products with identical SKU raises ValidationException."""
    unique_sku = f"TUB-UNIQUE-{uuid.uuid4().hex[:6]}"
    p1_in = ProductCreate(
        sku=unique_sku,
        name="Tub 1",
        slug=f"tub-1-{uuid.uuid4().hex[:6]}",
        material="Carrara Marble",
        base_price=Decimal("100000.00"),
    )
    ProductService.create_product(db=db_session, product_in=p1_in)

    p2_in = ProductCreate(
        sku=unique_sku,
        name="Tub 2",
        slug=f"tub-2-{uuid.uuid4().hex[:6]}",
        material="Carrara Marble",
        base_price=Decimal("120000.00"),
    )
    with pytest.raises(ValidationException):
        ProductService.create_product(db=db_session, product_in=p2_in)


def test_customer_normalization_and_deduplication(db_session: Session):
    """Verify phone/email normalization and deterministic lookup helper."""
    unique_id = uuid.uuid4().hex[:6]
    email = f"  Customer.{unique_id}@Example.COM  "
    raw_phone = "+91 (987) 654-3210"

    customer_in = CustomerCreate(
        first_name="Rohan",
        last_name="Verma",
        email=email,
        phone=raw_phone,
        whatsapp_number=raw_phone,
        source=CustomerSource.WEBSITE,
    )
    customer = CustomerService.create_customer(db=db_session, customer_in=customer_in)

    # Check normalization
    assert customer.email == f"customer.{unique_id}@example.com"
    assert customer.phone == "+919876543210"
    assert customer.whatsapp_number == "+919876543210"

    # Lookup by normalized email
    found_by_email = CustomerService.find_existing_customer(
        db=db_session, email=f"CUSTOMER.{unique_id}@example.com"
    )
    assert found_by_email is not None
    assert found_by_email.id == customer.id

    # Lookup by raw phone
    found_by_phone = CustomerService.find_existing_customer(
        db=db_session, phone="+91-987-654-3210"
    )
    assert found_by_phone is not None
    assert found_by_phone.id == customer.id

    # Disallow duplicate customer creation
    with pytest.raises(ValidationException):
        CustomerService.create_customer(db=db_session, customer_in=customer_in)


def test_lead_lifecycle_and_transition_rules(db_session: Session):
    """Verify Lead creation, relationship with Customer, and transition constraints."""
    customer = CustomerService.create_customer(
        db=db_session,
        customer_in=CustomerCreate(
            first_name="Aarav",
            last_name="Sharma",
            email=f"aarav.{uuid.uuid4().hex[:6]}@example.com",
        ),
    )

    lead_in = LeadCreate(
        customer_id=customer.id,
        source=CustomerSource.WHATSAPP,
        estimated_value=Decimal("250000.00"),
        currency="INR",
        priority=LeadPriority.HIGH,
        interest_description="Interested in carved freestanding bathtub",
    )
    lead = LeadService.create_lead(db=db_session, lead_in=lead_in)

    assert lead.id is not None
    assert lead.customer_id == customer.id
    assert lead.status == LeadStatus.NEW

    # Normal transition: NEW -> CONTACTED
    lead = LeadService.update_lead(
        db=db_session,
        lead_id=lead.id,
        updates=LeadUpdate(status=LeadStatus.CONTACTED),
    )
    assert lead.status == LeadStatus.CONTACTED

    lead = LeadService.update_lead(
        db=db_session,
        lead_id=lead.id,
        updates=LeadUpdate(status=LeadStatus.LOST),
    )
    assert lead.status == LeadStatus.LOST

    # Business rule: LOST -> WON cannot happen without re-qualification
    with pytest.raises(ValidationException):
        LeadService.update_lead(
            db=db_session,
            lead_id=lead.id,
            updates=LeadUpdate(status=LeadStatus.WON),
        )


def test_lead_product_association(db_session: Session):
    """Verify Lead to Product N-N relationship with quantity and notes."""
    customer = CustomerService.create_customer(
        db=db_session,
        customer_in=CustomerCreate(
            first_name="Meera",
            last_name="Patel",
            email=f"meera.{uuid.uuid4().hex[:6]}@example.com",
        ),
    )
    product = ProductService.create_product(
        db=db_session,
        product_in=ProductCreate(
            sku=f"TUB-ASSOC-{uuid.uuid4().hex[:6]}",
            name="Assoc Tub",
            slug=f"assoc-tub-{uuid.uuid4().hex[:6]}",
            material="White Makrana Marble",
            base_price=Decimal("150000.00"),
        ),
    )
    lead = LeadService.create_lead(
        db=db_session,
        lead_in=LeadCreate(
            customer_id=customer.id,
            source=CustomerSource.INSTAGRAM,
            products=[
                LeadProductCreate(
                    product_id=product.id,
                    quantity=2,
                    notes="Interested in master bath installation",
                )
            ],
        ),
    )

    retrieved_lead = LeadService.get_lead(db=db_session, lead_id=lead.id)
    assert retrieved_lead is not None
    assert len(retrieved_lead.products) == 1
    assert retrieved_lead.products[0].product_id == product.id
    assert retrieved_lead.products[0].quantity == 2


def test_conversation_and_message_ordering(db_session: Session):
    """Verify conversation message appending and chronological ordering."""
    customer = CustomerService.create_customer(
        db=db_session,
        customer_in=CustomerCreate(
            first_name="Kavita",
            last_name="Iyer",
            email=f"kavita.{uuid.uuid4().hex[:6]}@example.com",
        ),
    )

    conversation = Conversation(
        customer_id=customer.id,
        channel=Channel.WHATSAPP,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conversation)
    db_session.flush()

    m1 = MessageService.append_message(
        db=db_session,
        conversation_id=conversation.id,
        message_in=MessageCreate(
            content="Hello, what is the lead time for the Imperial tub?",
            direction=MessageDirection.INBOUND,
            sender_type=SenderType.CUSTOMER,
            message_type=MessageType.TEXT,
        ),
    )
    m2 = MessageService.append_message(
        db=db_session,
        conversation_id=conversation.id,
        message_in=MessageCreate(
            content="Hello Kavita, our standard lead time is 4 to 6 weeks.",
            direction=MessageDirection.OUTBOUND,
            sender_type=SenderType.AI,
            message_type=MessageType.TEXT,
        ),
    )

    messages, total = MessageService.list_messages(
        db=db_session,
        conversation_id=conversation.id,
        page_params=PageParams(page=1, page_size=50),
    )
    assert total >= 2
    assert messages[0].id == m1.id
    assert messages[1].id == m2.id
    assert messages[0].sent_at <= messages[1].sent_at


def test_followup_lifecycle_rules(db_session: Session):
    """Verify FollowUp state transitions and business constraint preventing COMPLETED -> PENDING."""
    customer = CustomerService.create_customer(
        db=db_session,
        customer_in=CustomerCreate(
            first_name="Vikram",
            last_name="Singhania",
            email=f"vikram.{uuid.uuid4().hex[:6]}@example.com",
        ),
    )
    lead = LeadService.create_lead(
        db=db_session,
        lead_in=LeadCreate(
            customer_id=customer.id,
            source=CustomerSource.DIRECT,
        ),
    )

    followup = FollowUpService.schedule_followup(
        db=db_session,
        followup_in=FollowUpCreate(
            lead_id=lead.id,
            customer_id=customer.id,
            channel=Channel.PHONE,
            reason="Follow up on custom sizing enquiry",
            scheduled_at=datetime.now(UTC) + timedelta(days=2),
        ),
    )
    assert followup.status == FollowUpStatus.PENDING

    # Transition to COMPLETED
    completed = FollowUpService.update_followup(
        db=db_session,
        followup_id=followup.id,
        updates=FollowUpUpdate(status=FollowUpStatus.COMPLETED),
    )
    assert completed.status == FollowUpStatus.COMPLETED
    assert completed.completed_at is not None

    # Constraint: COMPLETED cannot revert to PENDING
    with pytest.raises(ValidationException):
        FollowUpService.update_followup(
            db=db_session,
            followup_id=followup.id,
            updates=FollowUpUpdate(status=FollowUpStatus.PENDING),
        )


def test_agent_run_and_tool_call_traceability(db_session: Session):
    """Verify AgentRun and ToolCall relationship for AI observability."""
    customer = CustomerService.create_customer(
        db=db_session,
        customer_in=CustomerCreate(
            first_name="Dev",
            last_name="Kapoor",
            email=f"dev.{uuid.uuid4().hex[:6]}@example.com",
        ),
    )

    agent_run = AgentRun(
        agent_name="sales_qualification_agent",
        agent_version="1.0.0",
        customer_id=customer.id,
        status=AgentRunStatus.COMPLETED,
        input_summary="Customer requested quote for 72 inch marble bathtub",
        output_summary="Generated quote and scheduled consultation follow-up",
    )
    db_session.add(agent_run)
    db_session.flush()

    tc1 = ToolCall(
        agent_run_id=agent_run.id,
        tool_name="search_products",
        status=ToolCallStatus.SUCCEEDED,
        arguments={"material": "marble", "min_length": 180},
        result_summary={"matches_found": 3},
    )
    tc2 = ToolCall(
        agent_run_id=agent_run.id,
        tool_name="create_lead",
        status=ToolCallStatus.SUCCEEDED,
        arguments={"estimated_value": 185000},
        result_summary={"lead_id": str(uuid.uuid4())},
    )
    db_session.add_all([tc1, tc2])
    db_session.flush()

    assert len(agent_run.tool_calls) == 2
    assert agent_run.tool_calls[0].tool_name == "search_products"
    assert agent_run.tool_calls[1].tool_name == "create_lead"


def test_audit_log_creation_and_append_only(db_session: Session):
    """Verify AuditLog records system actions immutably."""
    entity_id = uuid.uuid4()
    audit_entry = AuditService.record(
        db=db_session,
        action="LEAD_STATUS_UPDATED",
        entity_type="lead",
        entity_id=entity_id,
        actor_type=ActorType.AI_AGENT,
        actor_id="sales_agent_v1",
        description="Lead status changed from NEW to QUALIFIED after budget confirmation",
        before_state={"status": "NEW"},
        after_state={"status": "QUALIFIED"},
        metadata={"confidence_score": 0.94},
    )

    assert audit_entry.id is not None
    assert audit_entry.action == "LEAD_STATUS_UPDATED"
    assert audit_entry.entity_id == str(entity_id)
    assert audit_entry.created_at is not None
