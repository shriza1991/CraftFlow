"""Deterministic database seed script for development and integration testing."""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models.agent_run import AgentRun
from app.db.models.audit_log import AuditLog
from app.db.models.conversation import Conversation
from app.db.models.customer import Customer
from app.db.models.enums import (
    ActorType,
    AgentRunStatus,
    Channel,
    ConversationStatus,
    CustomerSource,
    FollowUpStatus,
    LeadPriority,
    LeadStatus,
    MessageDirection,
    MessageStatus,
    MessageType,
    ProductAvailability,
    SenderType,
    ToolCallStatus,
)
from app.db.models.follow_up import FollowUp
from app.db.models.lead import Lead
from app.db.models.message import Message
from app.db.models.product import LeadProduct, Product, ProductVariant
from app.db.models.tool_call import ToolCall
from app.db.session import SessionLocal


def seed_database(reset: bool = False) -> dict[str, int]:
    """Populate database with rich, interconnected luxury bathtub synthetic domain data."""
    db: Session = SessionLocal()
    counts = {
        "products": 0,
        "variants": 0,
        "customers": 0,
        "leads": 0,
        "lead_products": 0,
        "conversations": 0,
        "messages": 0,
        "follow_ups": 0,
        "agent_runs": 0,
        "tool_calls": 0,
        "audit_logs": 0,
    }

    try:
        if reset:
            print("Clearing existing domain data for fresh deterministic seed...")
            # Delete in child-to-parent order to respect foreign keys
            db.execute(text("TRUNCATE TABLE tool_calls, agent_runs, audit_logs, follow_ups, messages, conversations, lead_products, leads, product_variants, products, customers CASCADE;"))
            db.commit()

        # Check if already seeded
        existing_products = db.scalar(select(Product.id))
        if existing_products and not reset:
            print("Database already contains product data. Use --reset to re-seed from scratch.")
            return counts

        now = datetime.now(UTC)

        # ----------------------------------------------------------------------
        # 1. PRODUCTS & VARIANTS
        # ----------------------------------------------------------------------
        products_data = [
            {
                "sku": "TUB-CAR-01",
                "name": "Carrara Monolithic Oval Bathtub",
                "slug": "carrara-monolithic-oval-bathtub",
                "short_description": "Hand-carved from a single solid block of Italian Bianco Carrara marble.",
                "description": "Each bathtub requires 120 artisan carving hours. Sculpted with a gently sloped interior and soft-radiused rim for ergonomic comfort.",
                "material": "Bianco Carrara Marble",
                "style": "Oval Freestanding",
                "category": "Bathtub",
                "length": Decimal("1800.00"),
                "width": Decimal("850.00"),
                "height": Decimal("580.00"),
                "weight": Decimal("680.00"),
                "base_price": Decimal("14500.00"),
                "currency": "USD",
                "lead_time_days": 60,
                "availability_status": ProductAvailability.MADE_TO_ORDER.value,
                "is_customizable": True,
                "is_active": True,
                "warranty_description": "10-year structural warranty against natural stone fissure defects.",
                "installation_notes": "Reinforced structural subfloor required. Minimum 750kg/m2 load capacity.",
                "shipping_notes": "Custom timber crating with shock-watch monitoring. White-glove insured freight.",
                "metadata_": {"origin": "Carrara, Italy", "finish_default": "Honed Matte"},
                "variants": [
                    {
                        "name": "Carrara Oval - Honed Matte (1800mm)",
                        "sku_suffix": "1800-HON",
                        "length": Decimal("1800.00"),
                        "width": Decimal("850.00"),
                        "height": Decimal("580.00"),
                        "finish": "Honed Matte",
                        "color": "Soft White with Grey Veining",
                        "price_adjustment": Decimal("0.00"),
                    },
                    {
                        "name": "Carrara Oval - Grand Length (1950mm)",
                        "sku_suffix": "1950-HON",
                        "length": Decimal("1950.00"),
                        "width": Decimal("900.00"),
                        "height": Decimal("600.00"),
                        "finish": "Honed Matte",
                        "color": "Soft White with Grey Veining",
                        "price_adjustment": Decimal("2200.00"),
                        "is_custom": True,
                    },
                ],
            },
            {
                "sku": "TUB-NERO-02",
                "name": "Nero Marquina Imperial Sculpted Bathtub",
                "slug": "nero-marquina-imperial-sculpted-bathtub",
                "short_description": "Deep black Spanish marble with striking crystalline calcite lightning veins.",
                "description": "Dramatic statement centerpiece. Hand-honed interior with optional chiseled exterior texture honoring natural quarry geology.",
                "material": "Nero Marquina Marble",
                "style": "Architectural Rectilinear",
                "category": "Bathtub",
                "length": Decimal("1900.00"),
                "width": Decimal("900.00"),
                "height": Decimal("600.00"),
                "weight": Decimal("740.00"),
                "base_price": Decimal("18800.00"),
                "currency": "USD",
                "lead_time_days": 75,
                "availability_status": ProductAvailability.MADE_TO_ORDER.value,
                "is_customizable": True,
                "is_active": True,
                "metadata_": {"origin": "Markina-Xemein, Spain", "finish_default": "Polished Satin"},
                "variants": [
                    {
                        "name": "Nero Marquina - Polished Satin",
                        "sku_suffix": "STD-POL",
                        "length": Decimal("1900.00"),
                        "width": Decimal("900.00"),
                        "height": Decimal("600.00"),
                        "finish": "Polished Satin",
                        "color": "Deep Carbon Black with White Veins",
                        "price_adjustment": Decimal("0.00"),
                    }
                ],
            },
            {
                "sku": "TUB-TRAV-03",
                "name": "Travertine Romano Classical Soaking Tub",
                "slug": "travertine-romano-classical-soaking-tub",
                "short_description": "Ancient Roman silver vein-cut travertine crafted with minimalist curved geometry.",
                "description": "Warm tactile stone featuring organic geological banding. Sealed with penetrating water-based siloxane impregnator.",
                "material": "Roman Silver Travertine",
                "style": "Minimalist Organic",
                "category": "Bathtub",
                "length": Decimal("1750.00"),
                "width": Decimal("800.00"),
                "height": Decimal("560.00"),
                "weight": Decimal("620.00"),
                "base_price": Decimal("13200.00"),
                "currency": "USD",
                "lead_time_days": 50,
                "availability_status": ProductAvailability.MADE_TO_ORDER.value,
                "is_customizable": True,
                "is_active": True,
                "metadata_": {"origin": "Tivoli, Italy", "finish_default": "Filled & Honed"},
                "variants": [
                    {
                        "name": "Travertine Romano - Filled & Honed",
                        "sku_suffix": "FILLED-HON",
                        "length": Decimal("1750.00"),
                        "width": Decimal("800.00"),
                        "height": Decimal("560.00"),
                        "finish": "Filled & Honed",
                        "color": "Silver Grey Beige",
                        "price_adjustment": Decimal("0.00"),
                    }
                ],
            },
            {
                "sku": "TUB-VIOLA-04",
                "name": "Calacatta Viola Heritage Fluted Tub",
                "slug": "calacatta-viola-heritage-fluted-tub",
                "short_description": "Rare Italian marble with rich cabernet wine veining and fluted artisan exterior.",
                "description": "Masterwork of stone relief carving. Each exterior flute is cut by hand to create architectural light and shadow play.",
                "material": "Calacatta Viola Marble",
                "style": "Fluted Classical",
                "category": "Bathtub",
                "length": Decimal("1850.00"),
                "width": Decimal("880.00"),
                "height": Decimal("620.00"),
                "weight": Decimal("790.00"),
                "base_price": Decimal("24500.00"),
                "currency": "USD",
                "lead_time_days": 90,
                "availability_status": ProductAvailability.MADE_TO_ORDER.value,
                "is_customizable": True,
                "is_active": True,
                "metadata_": {"origin": "Apuan Alps, Italy"},
                "variants": [
                    {
                        "name": "Calacatta Viola - Fluted Exterior",
                        "sku_suffix": "FLUTED-HON",
                        "length": Decimal("1850.00"),
                        "width": Decimal("880.00"),
                        "height": Decimal("620.00"),
                        "finish": "Honed Matte",
                        "color": "Cream with Purple-Burgundy Veins",
                        "price_adjustment": Decimal("0.00"),
                    }
                ],
            },
            {
                "sku": "TUB-VERDE-05",
                "name": "Verde Alpi Monolith Bathtub",
                "slug": "verde-alpi-monolith-bathtub",
                "short_description": "Spectacular serpentine green marble quarried in the Italian Alps.",
                "description": "Deep forest emerald green with white and pale green brecciated veins. Polished to a luxurious liquid luster.",
                "material": "Verde Alpi Marble",
                "style": "Sculptural Monolith",
                "category": "Bathtub",
                "length": Decimal("1800.00"),
                "width": Decimal("860.00"),
                "height": Decimal("570.00"),
                "weight": Decimal("710.00"),
                "base_price": Decimal("17900.00"),
                "currency": "USD",
                "lead_time_days": 60,
                "availability_status": ProductAvailability.MADE_TO_ORDER.value,
                "is_customizable": True,
                "is_active": True,
                "metadata_": {"origin": "Aosta Valley, Italy"},
                "variants": [
                    {
                        "name": "Verde Alpi - Polished Satin",
                        "sku_suffix": "SAT-POL",
                        "length": Decimal("1800.00"),
                        "width": Decimal("860.00"),
                        "height": Decimal("570.00"),
                        "finish": "Polished Satin",
                        "color": "Forest Green with Pale Calcite",
                        "price_adjustment": Decimal("0.00"),
                    }
                ],
            },
        ]

        products_map: dict[str, Product] = {}
        for p_info in products_data:
            variants_info = p_info.pop("variants")
            product = Product(**p_info)
            db.add(product)
            db.flush()
            products_map[product.sku] = product
            counts["products"] += 1

            for v_info in variants_info:
                variant = ProductVariant(product_id=product.id, **v_info)
                db.add(variant)
                counts["variants"] += 1

        db.flush()

        # ----------------------------------------------------------------------
        # 2. CUSTOMERS
        # ----------------------------------------------------------------------
        customers_data = [
            {
                "first_name": "Eleanor",
                "last_name": "Vance",
                "email": "eleanor@vance-interiors.com",
                "phone": "+1-212-555-0182",
                "whatsapp_number": "+12125550182",
                "company_name": "Vance Interior Architecture",
                "country": "United States",
                "city": "New York",
                "preferred_language": "en",
                "source": CustomerSource.WEBSITE.value,
                "status": "vip",
            },
            {
                "first_name": "Marcus",
                "last_name": "Chen",
                "email": "m.chen@apexhospitality.sg",
                "phone": "+65-6712-3456",
                "whatsapp_number": "+6567123456",
                "company_name": "Apex Hospitality Group",
                "country": "Singapore",
                "city": "Singapore",
                "preferred_language": "en",
                "source": CustomerSource.WHATSAPP.value,
                "status": "vip",
            },
            {
                "first_name": "Sofia",
                "last_name": "Lindqvist",
                "email": "sofia@nordicvillare.se",
                "phone": "+46-8-123-4567",
                "whatsapp_number": "+4681234567",
                "company_name": "Lindqvist Studio",
                "country": "Sweden",
                "city": "Stockholm",
                "preferred_language": "en",
                "source": CustomerSource.INSTAGRAM.value,
                "status": "active",
            },
            {
                "first_name": "David",
                "last_name": "Sterling",
                "email": "david.sterling@sterling-holdings.ch",
                "phone": "+41-44-555-7890",
                "whatsapp_number": "+41445557890",
                "company_name": "Sterling Capital",
                "country": "Switzerland",
                "city": "Zurich",
                "preferred_language": "en",
                "source": CustomerSource.REFERRAL.value,
                "status": "active",
            },
            {
                "first_name": "Amara",
                "last_name": "Al-Mansoor",
                "email": "amara.mansoor@desertpearl.ae",
                "phone": "+971-4-890-1234",
                "whatsapp_number": "+97148901234",
                "company_name": "Desert Pearl Estates",
                "country": "United Arab Emirates",
                "city": "Dubai",
                "preferred_language": "en",
                "source": CustomerSource.DIRECT.value,
                "status": "active",
            },
        ]

        customers_list: list[Customer] = []
        for c_data in customers_data:
            customer = Customer(**c_data)
            db.add(customer)
            customers_list.append(customer)
            counts["customers"] += 1
        db.flush()

        # ----------------------------------------------------------------------
        # 3. LEADS & LEAD-PRODUCT ASSOCIATIONS
        # ----------------------------------------------------------------------
        # Lead 1: Eleanor Vance interested in Carrara + Viola
        lead_1 = Lead(
            customer_id=customers_list[0].id,
            status=LeadStatus.QUALIFIED.value,
            source=CustomerSource.WEBSITE.value,
            estimated_value=Decimal("39000.00"),
            currency="USD",
            interest_description="Tribeca penthouse master bath renovation. Seeking Carrara monolithic tub and matching Viola powder room basin.",
            qualification_score=Decimal("92.50"),
            priority=LeadPriority.HIGH.value,
            assigned_to="Alexander Stone (Design Consultant)",
            expected_close_date=now + timedelta(days=30),
            last_contacted_at=now - timedelta(hours=4),
            next_follow_up_at=now + timedelta(days=2),
            notes="Client requested CAD 3D step files for architectural layout check.",
        )
        db.add(lead_1)
        db.flush()
        counts["leads"] += 1

        db.add(LeadProduct(lead_id=lead_1.id, product_id=products_map["TUB-CAR-01"].id, quantity=1, notes="1800mm standard"))
        db.add(LeadProduct(lead_id=lead_1.id, product_id=products_map["TUB-VIOLA-04"].id, quantity=1, notes="Powder room suite"))
        counts["lead_products"] += 2

        # Lead 2: Marcus Chen interested in Nero Marquina
        lead_2 = Lead(
            customer_id=customers_list[1].id,
            status=LeadStatus.PROPOSAL.value,
            source=CustomerSource.WHATSAPP.value,
            estimated_value=Decimal("56400.00"),
            currency="USD",
            interest_description="Boutique resort presidential suites in Sentosa. Requires 3 units of Nero Marquina Imperial tubs.",
            qualification_score=Decimal("95.00"),
            priority=LeadPriority.URGENT.value,
            assigned_to="Sarah Jenkins (Hospitality Director)",
            expected_close_date=now + timedelta(days=15),
            last_contacted_at=now - timedelta(days=1),
            next_follow_up_at=now + timedelta(days=1),
            notes="Formal commercial quote dispatched including Singapore sea freight insurance.",
        )
        db.add(lead_2)
        db.flush()
        counts["leads"] += 1

        db.add(LeadProduct(lead_id=lead_2.id, product_id=products_map["TUB-NERO-02"].id, quantity=3, notes="Resort villa master baths"))
        counts["lead_products"] += 1

        # Lead 3: Sofia Lindqvist interested in Travertine Romano
        lead_3 = Lead(
            customer_id=customers_list[2].id,
            status=LeadStatus.CONTACTED.value,
            source=CustomerSource.INSTAGRAM.value,
            estimated_value=Decimal("13200.00"),
            currency="USD",
            interest_description="Stockholm archipelago seaside retreat. Inquiring about travertine maintenance with underfloor heating.",
            qualification_score=Decimal("78.00"),
            priority=LeadPriority.MEDIUM.value,
            next_follow_up_at=now + timedelta(days=4),
        )
        db.add(lead_3)
        db.flush()
        counts["leads"] += 1
        db.add(LeadProduct(lead_id=lead_3.id, product_id=products_map["TUB-TRAV-03"].id, quantity=1))
        counts["lead_products"] += 1

        # Lead 4: David Sterling interested in Verde Alpi
        lead_4 = Lead(
            customer_id=customers_list[3].id,
            status=LeadStatus.NEGOTIATION.value,
            source=CustomerSource.REFERRAL.value,
            estimated_value=Decimal("17900.00"),
            currency="USD",
            interest_description="Lake Zurich private chalet spa bathroom.",
            qualification_score=Decimal("88.00"),
            priority=LeadPriority.HIGH.value,
            next_follow_up_at=now + timedelta(days=3),
        )
        db.add(lead_4)
        db.flush()
        counts["leads"] += 1
        db.add(LeadProduct(lead_id=lead_4.id, product_id=products_map["TUB-VERDE-05"].id, quantity=1))
        counts["lead_products"] += 1

        # Lead 5: Amara Al-Mansoor interested in Carrara Monolithic
        lead_5 = Lead(
            customer_id=customers_list[4].id,
            status=LeadStatus.NEW.value,
            source=CustomerSource.DIRECT.value,
            estimated_value=Decimal("16700.00"),
            currency="USD",
            interest_description="New villa build in Emirates Hills Dubai. Inquired via web form about white glove air freight.",
            priority=LeadPriority.MEDIUM.value,
            next_follow_up_at=now + timedelta(days=1),
        )
        db.add(lead_5)
        db.flush()
        counts["leads"] += 1
        db.add(LeadProduct(lead_id=lead_5.id, product_id=products_map["TUB-CAR-01"].id, quantity=1))
        counts["lead_products"] += 1
        db.flush()

        # ----------------------------------------------------------------------
        # 4. CONVERSATIONS & MESSAGES
        # ----------------------------------------------------------------------
        # Conversation 1: Eleanor Vance (WhatsApp)
        conv_1 = Conversation(
            customer_id=customers_list[0].id,
            channel=Channel.WHATSAPP.value,
            external_conversation_id="wa_chat_eleanor_vance",
            status=ConversationStatus.OPEN.value,
            started_at=now - timedelta(hours=6),
            last_message_at=now - timedelta(hours=4),
        )
        db.add(conv_1)
        db.flush()
        counts["conversations"] += 1

        msg_1 = Message(
            conversation_id=conv_1.id,
            direction=MessageDirection.INBOUND.value,
            message_type=MessageType.TEXT.value,
            sender_type=SenderType.CUSTOMER.value,
            status=MessageStatus.READ.value,
            content="Hello Ages Art, I am specifying a solid marble tub for a Manhattan penthouse. Do you have the Carrara Monolithic in stock, and what is the weight?",
            sent_at=now - timedelta(hours=6),
        )
        msg_2 = Message(
            conversation_id=conv_1.id,
            direction=MessageDirection.OUTBOUND.value,
            message_type=MessageType.TEXT.value,
            sender_type=SenderType.AI.value,
            status=MessageStatus.DELIVERED.value,
            content="Welcome Eleanor. Our Carrara Monolithic Oval Bathtub is carved from single blocks of Italian Bianco Carrara. The standard 1800mm length weighs approximately 680 kg (dry). Each piece is sculpted to order with an 8-week artisan lead time. Would you like our structural load specification sheet?",
            sent_at=now - timedelta(hours=5, minutes=58),
        )
        msg_3 = Message(
            conversation_id=conv_1.id,
            direction=MessageDirection.INBOUND.value,
            message_type=MessageType.TEXT.value,
            sender_type=SenderType.CUSTOMER.value,
            status=MessageStatus.READ.value,
            content="Yes please, and kindly email the 3D step CAD files to eleanor@vance-interiors.com.",
            sent_at=now - timedelta(hours=4),
        )
        db.add_all([msg_1, msg_2, msg_3])
        counts["messages"] += 3

        # Conversation 2: Marcus Chen (Website)
        conv_2 = Conversation(
            customer_id=customers_list[1].id,
            channel=Channel.WEBSITE.value,
            external_conversation_id="web_chat_marcus_chen",
            status=ConversationStatus.OPEN.value,
            started_at=now - timedelta(days=1),
            last_message_at=now - timedelta(hours=18),
        )
        db.add(conv_2)
        db.flush()
        counts["conversations"] += 1

        msg_4 = Message(
            conversation_id=conv_2.id,
            direction=MessageDirection.INBOUND.value,
            content="Good morning. We require 3 Nero Marquina bathtubs for a luxury villa project in Singapore.",
            sent_at=now - timedelta(days=1),
        )
        msg_5 = Message(
            conversation_id=conv_2.id,
            direction=MessageDirection.OUTBOUND.value,
            sender_type=SenderType.AI.value,
            content="Good morning Marcus. We would be pleased to assist Apex Hospitality Group. For multiple units, our master sculptors select sequentially quarried stone blocks to ensure harmonious vein patterns. I have generated a formal hospitality quotation for 3 Nero Marquina units.",
            sent_at=now - timedelta(days=1, minutes=-2),
        )
        db.add_all([msg_4, msg_5])
        counts["messages"] += 2
        db.flush()

        # ----------------------------------------------------------------------
        # 5. FOLLOW-UPS
        # ----------------------------------------------------------------------
        fu_1 = FollowUp(
            lead_id=lead_1.id,
            customer_id=customers_list[0].id,
            conversation_id=conv_1.id,
            channel=Channel.WHATSAPP.value,
            scheduled_at=now + timedelta(days=2),
            status=FollowUpStatus.SCHEDULED.value,
            reason="Confirm architectural subfloor review and delivery access for Tribeca penthouse.",
            message_template="Hi Eleanor, following up to confirm if your structural engineer reviewed the 680kg load calculations for the Carrara Monolithic tub.",
        )
        fu_2 = FollowUp(
            lead_id=lead_2.id,
            customer_id=customers_list[1].id,
            conversation_id=conv_2.id,
            channel=Channel.EMAIL.value,
            scheduled_at=now + timedelta(days=1),
            status=FollowUpStatus.PENDING.value,
            reason="Follow-up on multi-unit commercial proposal and delivery schedule for Sentosa villas.",
        )
        db.add_all([fu_1, fu_2])
        counts["follow_ups"] += 2
        db.flush()

        # ----------------------------------------------------------------------
        # 6. AGENT RUNS & TOOL CALLS
        # ----------------------------------------------------------------------
        agent_run = AgentRun(
            agent_name="SalesQualificationAgent",
            agent_version="1.0.0",
            conversation_id=conv_1.id,
            customer_id=customers_list[0].id,
            lead_id=lead_1.id,
            status=AgentRunStatus.COMPLETED.value,
            input_summary="Customer inquiring about Carrara bathtub weight and availability for penthouse project.",
            output_summary="Verified stone specs, calculated weight (680kg), dispatched CAD specs, and initiated high-priority lead.",
            started_at=now - timedelta(hours=6),
            completed_at=now - timedelta(hours=5, minutes=58),
            metadata_={"model": "gpt-4o-mini", "execution_time_ms": 1420},
        )
        db.add(agent_run)
        db.flush()
        counts["agent_runs"] += 1

        tool_call_1 = ToolCall(
            agent_run_id=agent_run.id,
            tool_name="search_products",
            status=ToolCallStatus.SUCCEEDED.value,
            arguments={"query": "Carrara Monolithic", "category": "Bathtub"},
            result_summary={"matches_found": 1, "sku": "TUB-CAR-01", "base_price": 14500},
            started_at=now - timedelta(hours=6),
            completed_at=now - timedelta(hours=5, minutes=59),
        )
        tool_call_2 = ToolCall(
            agent_run_id=agent_run.id,
            tool_name="create_lead",
            status=ToolCallStatus.SUCCEEDED.value,
            arguments={"customer_id": customers_list[0].id, "priority": "HIGH", "estimated_value": 39000},
            result_summary={"lead_id": lead_1.id, "status": "QUALIFIED"},
            started_at=now - timedelta(hours=5, minutes=59),
            completed_at=now - timedelta(hours=5, minutes=58),
        )
        db.add_all([tool_call_1, tool_call_2])
        counts["tool_calls"] += 2
        db.flush()

        # ----------------------------------------------------------------------
        # 7. AUDIT LOGS
        # ----------------------------------------------------------------------
        audit_1 = AuditLog(
            actor_type=ActorType.SYSTEM.value,
            action="SYSTEM_SEED_INITIALIZED",
            entity_type="System",
            entity_id="craftflow_seed",
            description="Loaded deterministic synthetic baseline luxury bathtub catalog and customer records.",
            metadata_={"environment": "development"},
            created_at=now,
        )
        audit_2 = AuditLog(
            actor_type=ActorType.AI_AGENT.value,
            actor_id="SalesQualificationAgent",
            action="LEAD_QUALIFIED",
            entity_type="Lead",
            entity_id=lead_1.id,
            description="Automatically qualified lead based on commercial budget and architectural timeline.",
            before_state={"status": "NEW"},
            after_state={"status": "QUALIFIED", "score": "92.50"},
            created_at=now - timedelta(hours=5, minutes=58),
        )
        db.add_all([audit_1, audit_2])
        counts["audit_logs"] += 2

        db.commit()
        print(f"Successfully seeded database: {counts}")
        return counts

    except Exception as exc:
        db.rollback()
        print(f"Error during seed: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Seed CraftFlow PostgreSQL database with luxury bathtub domain data.")
    parser.add_argument("--reset", action="store_true", help="Truncate existing tables before seeding")
    args = parser.parse_args()
    seed_database(reset=args.reset)


if __name__ == "__main__":
    main()
