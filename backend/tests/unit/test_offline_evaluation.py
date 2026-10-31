"""Offline regression coverage through actual inquiry service orchestration."""

import pytest
from app.evaluation.runner import evaluate_case, load_dataset


@pytest.mark.asyncio
@pytest.mark.parametrize("business", load_dataset()["businesses"], ids=lambda b: b["id"])
@pytest.mark.parametrize("scenario", load_dataset()["scenarios"])
async def test_inquiry_contracts_across_businesses(business, scenario):
    result = await evaluate_case(business, scenario)
    assert result["error"] is None, result
    assert result["passed"], result["checks"]
