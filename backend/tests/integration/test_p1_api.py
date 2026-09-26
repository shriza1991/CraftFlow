"""Integration tests for P1 domain REST APIs against real PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def test_products_api_crud(client_with_db: TestClient):
    """Test full CRUD lifecycle for Products via REST API."""
    unique_sku = f"TUB-API-{uuid.uuid4().hex[:6]}"
    product_payload = {
        "sku": unique_sku,
        "name": "Handmade Heritage Tub",
        "slug": f"handmade-heritage-tub-{uuid.uuid4().hex[:6]}",
        "material": "Makrana White Marble",
        "category": "freestanding",
        "base_price": "220000.00",
        "currency": "INR",
        "length": "185.00",
        "width": "85.00",
        "height": "62.00",
        "weight": "420.00",
        "lead_time_days": 35,
        "availability_status": "MADE_TO_ORDER",
        "is_active": True,
        "variants": [
            {
                "name": "Polished High Gloss",
                "sku_suffix": "PHG",
                "material": "Makrana White Marble",
                "finish": "Polished Gloss",
                "color": "Pure White",
                "price_adjustment": "20000.00",
            }
        ],
    }

    # 1. POST create product
    create_resp = client_with_db.post("/api/v1/products", json=product_payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    product_id = created_data["id"]
    assert created_data["sku"] == unique_sku
    assert len(created_data["variants"]) == 1

    # 2. GET list products with pagination
    list_resp = client_with_db.get("/api/v1/products?page=1&page_size=10")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(p["id"] == product_id for p in list_data["items"])

    # 3. GET product by ID
    get_resp = client_with_db.get(f"/api/v1/products/{product_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == product_id

    # 4. PATCH update product
    patch_resp = client_with_db.patch(
        f"/api/v1/products/{product_id}",
        json={"base_price": "235000.00", "lead_time_days": 40},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["base_price"] == "235000.00"
    assert patch_resp.json()["lead_time_days"] == 40

    # 5. 404 for nonexistent product
    not_found_resp = client_with_db.get(f"/api/v1/products/{uuid.uuid4()}")
    assert not_found_resp.status_code == 404

    # 6. 422 for invalid payload (negative price)
    bad_resp = client_with_db.post(
        "/api/v1/products",
        json={**product_payload, "sku": f"ERR-{uuid.uuid4().hex[:6]}", "base_price": "-500.00"},
    )
    assert bad_resp.status_code == 422


def test_customers_api_crud(client_with_db: TestClient):
    """Test full CRUD lifecycle and deduplication for Customers via REST API."""
    unique_email = f"lead.{uuid.uuid4().hex[:6]}@luxuryestates.com"
    customer_payload = {
        "first_name": "Rajesh",
        "last_name": "Mehta",
        "email": unique_email,
        "phone": "+91 9988776655",
        "whatsapp_number": "+91 9988776655",
        "city": "Mumbai",
        "country": "India",
        "source": "WEBSITE",
    }

    # 1. POST create customer
    create_resp = client_with_db.post("/api/v1/customers", json=customer_payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    customer_id = created_data["id"]
    assert created_data["first_name"] == "Rajesh"
    assert created_data["phone"] == "+919988776655"

    # 2. GET list customers with pagination
    list_resp = client_with_db.get("/api/v1/customers?page=1&page_size=10")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1

    # 3. GET customer by ID
    get_resp = client_with_db.get(f"/api/v1/customers/{customer_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == unique_email

    # 4. PATCH update customer
    patch_resp = client_with_db.patch(
        f"/api/v1/customers/{customer_id}",
        json={"city": "South Mumbai", "company_name": "Mehta Luxury Living"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["city"] == "South Mumbai"
    assert patch_resp.json()["company_name"] == "Mehta Luxury Living"

    # 5. 422 on duplicate customer creation
    dup_resp = client_with_db.post("/api/v1/customers", json=customer_payload)
    assert dup_resp.status_code == 422


def test_leads_api_and_state_rules(client_with_db: TestClient):
    """Test Lead creation, product linking, and state machine transition rules via REST API."""
    # 1. Setup Customer and Product
    cust_resp = client_with_db.post(
        "/api/v1/customers",
        json={
            "first_name": "Siddharth",
            "last_name": "Roy",
            "email": f"sid.{uuid.uuid4().hex[:6]}@example.com",
            "source": "INSTAGRAM",
        },
    )
    cust_id = cust_resp.json()["id"]

    prod_resp = client_with_db.post(
        "/api/v1/products",
        json={
            "sku": f"TUB-LEAD-{uuid.uuid4().hex[:6]}",
            "name": "Luxury Bathtub for Lead Test",
            "slug": f"tub-lead-{uuid.uuid4().hex[:6]}",
            "material": "Italian Statuario",
            "base_price": "310000.00",
        },
    )
    prod_id = prod_resp.json()["id"]

    # 2. POST create lead
    lead_payload = {
        "customer_id": cust_id,
        "source": "INSTAGRAM",
        "estimated_value": "310000.00",
        "currency": "INR",
        "priority": "HIGH",
        "interest_description": "Penthouse villa bathtub requirements",
        "products": [
            {
                "product_id": prod_id,
                "quantity": 1,
                "notes": "Custom brass drain fittings requested",
            }
        ],
    }
    create_resp = client_with_db.post("/api/v1/leads", json=lead_payload)
    assert create_resp.status_code == 201
    lead_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "NEW"
    assert len(create_resp.json()["products"]) == 1

    # 3. GET list leads with status filter
    list_resp = client_with_db.get("/api/v1/leads?status=NEW&page=1&page_size=10")
    assert list_resp.status_code == 200
    assert any(lead["id"] == lead_id for lead in list_resp.json()["items"])

    # 4. PATCH update status: NEW -> LOST
    patch_resp = client_with_db.patch(
        f"/api/v1/leads/{lead_id}",
        json={"status": "LOST"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "LOST"

    # 5. PATCH invalid transition: LOST -> WON should fail with 422
    invalid_resp = client_with_db.patch(
        f"/api/v1/leads/{lead_id}",
        json={"status": "WON"},
    )
    assert invalid_resp.status_code == 422


def test_conversations_and_messages_api(client_with_db: TestClient):
    """Test conversation thread creation and message appending via REST API."""
    cust_resp = client_with_db.post(
        "/api/v1/customers",
        json={
            "first_name": "Pooja",
            "last_name": "Bhatia",
            "email": f"pooja.{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+91 9123456780",
            "source": "WHATSAPP",
        },
    )
    cust_id = cust_resp.json()["id"]

    # 1. POST create conversation
    conv_resp = client_with_db.post(
        "/api/v1/conversations",
        json={
            "customer_id": cust_id,
            "channel": "WHATSAPP",
            "external_conversation_id": f"wa-conv-{uuid.uuid4().hex[:8]}",
        },
    )
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]
    assert conv_resp.json()["status"] == "OPEN"

    # 2. POST message 1 (customer inbound)
    msg1_resp = client_with_db.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={
            "direction": "INBOUND",
            "sender_type": "CUSTOMER",
            "message_type": "TEXT",
            "content": "Can you ship to Goa and install on the 2nd floor?",
        },
    )
    assert msg1_resp.status_code == 201
    assert msg1_resp.json()["sender_type"] == "CUSTOMER"

    # 3. POST message 2 (AI outbound)
    msg2_resp = client_with_db.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={
            "direction": "OUTBOUND",
            "sender_type": "AI",
            "message_type": "TEXT",
            "content": "Yes Pooja, we deliver across India with crated logistics and installation guidance.",
        },
    )
    assert msg2_resp.status_code == 201

    # 4. GET list messages in conversation
    msgs_resp = client_with_db.get(f"/api/v1/conversations/{conv_id}/messages")
    assert msgs_resp.status_code == 200
    msgs_data = msgs_resp.json()
    assert msgs_data["total"] >= 2
    assert msgs_data["items"][0]["direction"] == "INBOUND"
    assert msgs_data["items"][1]["direction"] == "OUTBOUND"


def test_followups_api(client_with_db: TestClient):
    """Test follow-up scheduling, listing, and completion via REST API."""
    cust_resp = client_with_db.post(
        "/api/v1/customers",
        json={
            "first_name": "Arjun",
            "last_name": "Nair",
            "email": f"arjun.{uuid.uuid4().hex[:6]}@example.com",
            "source": "DIRECT",
        },
    )
    cust_id = cust_resp.json()["id"]

    lead_resp = client_with_db.post(
        "/api/v1/leads",
        json={
            "customer_id": cust_id,
            "source": "DIRECT",
            "priority": "HIGH",
        },
    )
    lead_id = lead_resp.json()["id"]

    scheduled_time = (datetime.now(UTC) + timedelta(days=3)).isoformat()

    # 1. POST schedule follow-up
    fu_resp = client_with_db.post(
        "/api/v1/followups",
        json={
            "lead_id": lead_id,
            "customer_id": cust_id,
            "channel": "WHATSAPP",
            "scheduled_at": scheduled_time,
            "reason": "Send luxury finish catalogue and sample stones",
        },
    )
    assert fu_resp.status_code == 201
    fu_id = fu_resp.json()["id"]
    assert fu_resp.json()["status"] == "PENDING"

    # 2. GET list followups
    list_resp = client_with_db.get("/api/v1/followups?status=PENDING&page=1&page_size=10")
    assert list_resp.status_code == 200
    assert any(fu["id"] == fu_id for fu in list_resp.json()["items"])

    # 3. PATCH complete follow-up
    patch_resp = client_with_db.patch(
        f"/api/v1/followups/{fu_id}",
        json={"status": "COMPLETED"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "COMPLETED"
    assert patch_resp.json()["completed_at"] is not None


def test_database_readiness_against_real_db(client_with_db: TestClient):
    """Test GET /api/v1/readiness verifies live PostgreSQL connection."""
    resp = client_with_db.get("/api/v1/readiness")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["dependencies"]["database"] == "healthy"
