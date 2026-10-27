"""Behavior across different business configurations and catalog domains."""

from decimal import Decimal

import pytest
from app.agents.demo import DemoAgent
from app.ai.providers.mock_provider import MockLLMProvider
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import *  # noqa: F403  # register models with metadata
from app.main import app
from app.rag.mock import MockRetriever
from app.schemas.product import ProductCreate
from app.services.product_service import ProductService
from app.tools.demo import MockProductSearchTool
from app.tools.registry import ToolRegistry
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.mark.parametrize(
    ("name", "description", "industry"),
    [("Ages Art", "Handmade stone products", "manufacturing"),
     ("Northstar Studio", "Interior design consultations", "professional services")],
)
def test_configured_business_endpoint(monkeypatch, name, description, industry):
    monkeypatch.setenv("BUSINESS_NAME", name)
    monkeypatch.setenv("BUSINESS_DESCRIPTION", description)
    monkeypatch.setenv("BUSINESS_INDUSTRY", industry)
    get_settings.cache_clear()
    with TestClient(app) as client:
        response = client.get("/api/v1/business")
    assert response.status_code == 200
    assert response.json() == {"name": name, "description": description, "industry": industry}


def test_catalog_supports_service_and_manufactured_product():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        service = ProductService.create_product(db, ProductCreate(
            sku="CONSULT-01", name="Consultation", slug="consultation",
            category="Services", base_price=Decimal("100"),
            metadata={"duration_minutes": 60},
        ))
        product = ProductService.create_product(db, ProductCreate(
            sku="TUB-01", name="Stone tub", slug="stone-tub", material="Marble",
            category="Bathtub", base_price=Decimal("12000"),
        ))
        assert service.material is None
        assert service.category == "Services"
        assert service.metadata_["duration_minutes"] == 60
        assert product.material == "Marble"
        assert ProductService.get_product(db, service.id).name == "Consultation"
    engine.dispose()


@pytest.mark.asyncio
async def test_demo_uses_business_identity_and_user_query(monkeypatch):
    monkeypatch.setenv("BUSINESS_NAME", "Northstar Studio")
    monkeypatch.setenv("BUSINESS_DESCRIPTION", "Interior design consultations")
    get_settings.cache_clear()
    llm = MockLLMProvider()
    registry = ToolRegistry()
    registry.register(MockProductSearchTool([{"name": "Design consultation"}]))
    agent = DemoAgent(llm_provider=llm, tool_registry=registry)
    result = await agent.run("Search products for design")
    assert "Northstar Studio" in llm.history[-1][0].content
    assert result.tool_calls[0]["arguments"]["query"] == "Search products for design"
    assert result.tool_calls[0]["result"]["data"][0]["name"] == "Design consultation"


@pytest.mark.asyncio
async def test_mocks_do_not_return_another_business_data():
    assert (await MockProductSearchTool().execute({"query": "marble"})).data == []
    assert (await MockRetriever().search("marble")).chunks == []
