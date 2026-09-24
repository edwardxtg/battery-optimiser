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
    body = {"battery": {"capacity_mwh": 20.0, "power_mw": 10.0, "initial_soc_mwh": 2.0},
            "prices": prices}
    r = client.post("/optimise", json=body)
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "client"
    assert len(d["charge_mw"]) == len(prices)
    assert d["net_profit"] > 0
    assert d["cycles"] > 0
    assert d["gbp_per_mw_year"] > 0


def test_oversized_payload_rejected():
    # A prices array longer than the 336-period cap must be rejected (422), not processed.
    body = {"prices": [50.0] * 5000}
    r = client.post("/optimise", json=body)
    assert r.status_code == 422


def test_floor_above_soc_rejected():
    # A SoC floor above the current SoC is inconsistent input; expect a clean 422, not a 500.
    body = {"battery": {"capacity_mwh": 20.0, "power_mw": 10.0,
                        "initial_soc_mwh": 2.0, "soc_min_mwh": 5.0}}
    r = client.post("/optimise", json=body)
    assert r.status_code == 422
