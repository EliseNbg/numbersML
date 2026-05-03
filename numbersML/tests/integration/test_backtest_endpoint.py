"""
Integration tests for Backtest API endpoints.
"""

from fastapi.testclient import TestClient

from src.infrastructure.api.app import create_app

client = TestClient(create_app())


def test_backtest_models_list_endpoint():
    """Test GET /api/backtest_ml/models/entry endpoint returns valid response"""
    response = client.get("/api/backtest_ml/models/entry")

    # Should always return 200 even when no models exist
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_backtest_endpoint_validation():
    """Test backtest endpoint parameter validation"""
    # Missing required parameters
    response = client.get("/api/backtest_ml/entry")
    assert response.status_code == 422

    # Invalid threshold
    response = client.get("/api/backtest_ml/entry?symbol=BTC/USDC&model=test.pkl&threshold=1.5")
    assert response.status_code == 422

    response = client.get("/api/backtest_ml/entry?symbol=BTC/USDC&model=test.pkl&threshold=0.4")
    assert response.status_code == 422


def test_backtest_endpoint_unknown_symbol():
    """Test backtest endpoint with non-existing symbol"""
    response = client.get("/api/backtest_ml/entry?symbol=UNKNOWN/XXX&model=test.pkl&seconds=86400")
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
