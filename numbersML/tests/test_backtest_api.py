"""
Unit tests for Backtest API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.api.app import create_app

client = TestClient(create_app())


def test_list_models_endpoint():
    """Test GET /api/backtest_ml/models/entry endpoint"""
    response = client.get("/api/backtest_ml/models/entry")
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)


def test_backtest_endpoint_parameters():
    """Test backtest endpoint parameter validation for TradingTCN"""
    # Missing symbol
    response = client.get("/api/backtest_ml/trading_tcn")
    assert response.status_code == 422

    # With valid parameters (no specific validation on score_threshold)
    response = client.get("/api/backtest_ml/trading_tcn?symbol=BTC/USDC&model=test.pt&score_threshold=1.5")
    # Should not be 422 (param validation error)
    assert response.status_code != 422


def test_list_trading_tcn_models_endpoint():
    """Test GET /api/backtest_ml/models/trading_tcn endpoint"""
    response = client.get("/api/backtest_ml/models/trading_tcn")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_trading_tcn_backtest_endpoint_parameters():
    """Test TradingTCN backtest endpoint parameter validation"""
    # Missing symbol
    response = client.get("/api/backtest_ml/trading_tcn")
    assert response.status_code == 422

    # With symbol and model (validation passes, may fail later due to no DB)
    response = client.get("/api/backtest_ml/trading_tcn?symbol=DASH/USDC&model=test.pt")
    # Should not be 422 (param validation error)
    assert response.status_code != 422
