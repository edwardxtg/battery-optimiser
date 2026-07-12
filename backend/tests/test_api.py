"""API + parser tests using FastAPI's TestClient and representative payloads."""
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.data import _parse_elexon_mid

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_parse_elexon_mid():
    payload = {"data": [
        {"startTime": "2024-06-01T00:00:00Z", "price": 61.5},
        {"startTime": "2024-06-01T00:30:00Z", "price": 58.0},
    ]}
    s = _parse_elexon_mid(payload)
    assert list(s.values) == [61.5, 58.0]


def test_optimise_with_client_prices():
    prices = ([20.0] * 12 + [100.0] * 24 + [250.0] * 4 + [100.0] * 8)
    body = {"battery": {"capacity_kwh": 13.5, "power_kw": 5.0, "initial_soc_kwh": 2.0},
            "prices": prices}
    r = client.post("/optimise", json=body)
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "client"
    assert len(d["charge_kw"]) == len(prices)
    assert d["net_profit"] > 0


def test_oversized_payload_rejected():
    # A prices array longer than the 336-period cap must be rejected (422), not processed.
    body = {"prices": [50.0] * 5000}
    r = client.post("/optimise", json=body)
    assert r.status_code == 422


def test_reserve_above_soc_rejected():
    # Reserve above current SoC is inconsistent input; expect a clean 422, not a 500.
    body = {"battery": {"capacity_kwh": 13.5, "power_kw": 5.0,
                        "initial_soc_kwh": 2.0, "reserve_kwh": 5.0}}
    r = client.post("/optimise", json=body)
    assert r.status_code == 422
