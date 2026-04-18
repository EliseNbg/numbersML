"""
Unit tests for Backtest API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.api.app import create_app

client = TestClient(create_app())


def test_list_models_endpoint():
    """Test GET /api/backtest/models/entry endpoint"""
    response = client.get("/api/backtest/models/entry")
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)


def test_backtest_endpoint_parameters():
    """Test backtest endpoint parameter validation"""
    # Missing symbol
    response = client.get("/api/backtest/entry")
    assert response.status_code == 422

    # Invalid threshold
    response = client.get("/api/backtest/entry?symbol=BTC/USDC&model=test.pkl&threshold=1.5")
    assert response.status_code == 422

    response = client.get("/api/backtest/entry?symbol=BTC/USDC&model=test.pkl&threshold=0.4")
    assert response.status_code == 422
