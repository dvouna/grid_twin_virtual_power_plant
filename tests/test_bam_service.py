"""
D2: Unit tests for the BAM Service FastAPI endpoints.

Uses FastAPI's TestClient so no live server or InfluxDB is required.
InfluxDB calls (_persist_state, _restore_state, _write_dispatch_log)
are mocked so tests are fully self-contained and fast.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# --- Test client setup ---
# Patch InfluxDB at module level before importing the app so no real
# DB connection is attempted during tests.
_INFLUX_PATCH = "vpp.agents.battery_manager.InfluxDBClient"

# Provide a valid API key for all authenticated tests
TEST_API_KEY = "test-secret-key-123"
os.environ["BAM_API_KEY"] = TEST_API_KEY
# Prevent env-var driven capacity from affecting test isolation
os.environ.setdefault("BAM_CAPACITY_KWH", "10000.0")
os.environ.setdefault("BAM_MAX_C_RATE",   "1.0")
os.environ.setdefault("BAM_WEAR_COST",    "0.015")


@pytest.fixture(autouse=True)
def mock_influxdb():
    """Suppress all real InfluxDB writes/reads in every test."""
    with patch(_INFLUX_PATCH) as MockClient:
        instance = MagicMock()
        MockClient.return_value = instance
        instance.query_api.return_value.query.return_value = []
        yield instance


@pytest.fixture()
def client():
    """Return a fresh TestClient with a clean BAM agent for each test."""
    # Re-import app each fixture so bam_service starts at 50% SoC
    from vpp.agents.battery_manager import app, bam_service
    bam_service.current_soc_kwh = bam_service.capacity_kwh * 0.50
    return TestClient(app)


AUTH = {"X-BAM-API-Key": TEST_API_KEY}

# ─────────────────────────────────────────────
# /state endpoint (open — no auth required)
# ─────────────────────────────────────────────

class TestGetState:
    def test_returns_expected_schema(self, client):
        resp = client.get("/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_soc_kwh" in data
        assert "soc_percentage"  in data
        assert "capacity_kwh"    in data
        assert "max_dispatch_kw" in data

    def test_initial_soc_is_50_percent(self, client):
        resp = client.get("/state")
        assert resp.json()["soc_percentage"] == pytest.approx(0.50)

    def test_accessible_without_api_key(self, client):
        resp = client.get("/state")   # no header
        assert resp.status_code == 200


# ─────────────────────────────────────────────
# D1: Auth enforcement on /dispatch
# ─────────────────────────────────────────────

class TestApiKeyAuth:
    def test_dispatch_rejected_without_key(self, client):
        payload = {"agent_name": "Test", "requested_kw": 1000.0}
        resp = client.post("/dispatch", json=payload)  # no header
        assert resp.status_code == 403

    def test_dispatch_rejected_with_wrong_key(self, client):
        payload = {"agent_name": "Test", "requested_kw": 1000.0}
        resp = client.post("/dispatch", json=payload,
                           headers={"X-BAM-API-Key": "wrong-key"})
        assert resp.status_code == 403

    def test_pre_condition_rejected_without_key(self, client):
        payload = {"predicted_load_curve": [100.0, 200.0]}
        resp = client.post("/pre_condition", json=payload)
        assert resp.status_code == 403

    def test_dispatch_accepted_with_correct_key(self, client):
        payload = {"agent_name": "Test", "requested_kw": 1000.0}
        resp = client.post("/dispatch", json=payload, headers=AUTH)
        assert resp.status_code == 200


# ─────────────────────────────────────────────
# /dispatch endpoint — status labels
# ─────────────────────────────────────────────

class TestDispatch:
    def test_approved_normal_charge(self, client):
        """A request within C-Rate and SoC bounds should be APPROVED."""
        payload = {
            "agent_name": "ArbitrageTrader",
            "requested_kw": 1000.0,
            "duration_hours": 5 / 60,
        }
        resp = client.post("/dispatch", json=payload, headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "APPROVED"
        assert data["approved_kw"] == pytest.approx(1000.0)

    def test_scaled_when_exceeds_c_rate(self, client):
        """A 2C request should be scaled down to 1C."""
        from vpp.agents.battery_manager import bam_service
        capacity = bam_service.capacity_kwh
        payload = {
            "agent_name": "GridResponseActor",
            "requested_kw": capacity * 2,   # 2C, over the limit
            "duration_hours": 5 / 60,
        }
        resp = client.post("/dispatch", json=payload, headers=AUTH)
        data = resp.json()
        assert data["status"] == "SCALED"
        assert data["approved_kw"] <= bam_service.max_dispatch_kw

    def test_denied_when_soc_at_zero(self, client):
        """Discharge request when SoC is 0 should produce 0 kW approved."""
        from vpp.agents.battery_manager import bam_service
        bam_service.current_soc_kwh = 0.0
        payload = {
            "agent_name": "GridResponseActor",
            "requested_kw": -5000.0,
            "duration_hours": 5 / 60,
        }
        resp = client.post("/dispatch", json=payload, headers=AUTH)
        data = resp.json()
        assert data["approved_kw"] == pytest.approx(0.0)
        assert data["status"] == "DENIED"

    def test_denied_by_economic_veto(self, client):
        """Revenue below degradation cost should be vetoed."""
        # 5000 kW * (5/60 h) = 416.7 kWh * $0.015 = $6.25 wear cost
        # Supplying only $1 expected revenue → veto
        payload = {
            "agent_name":                "ArbitrageTrader",
            "requested_kw":              -5000.0,
            "duration_hours":            5 / 60,
            "expected_revenue_per_kwh":  1.0,
        }
        resp = client.post("/dispatch", json=payload, headers=AUTH)
        data = resp.json()
        assert data["approved_kw"] == pytest.approx(0.0)
        assert data["status"] == "DENIED"

    def test_soc_updates_after_approved_dispatch(self, client):
        """SoC should increase after a successful charge dispatch."""
        from vpp.agents.battery_manager import bam_service
        initial_soc = bam_service.current_soc_kwh
        payload = {
            "agent_name":   "ArbitrageTrader",
            "requested_kw": 5000.0,
            "duration_hours": 1.0,
        }
        client.post("/dispatch", json=payload, headers=AUTH)
        assert bam_service.current_soc_kwh > initial_soc


# ─────────────────────────────────────────────
# /pre_condition endpoint
# ─────────────────────────────────────────────

class TestPreCondition:
    def test_no_dispatch_for_flat_curve(self, client):
        """A flat, low load curve should not trigger pre-conditioning."""
        payload = {"predicted_load_curve": [50000.0, 52000.0, 51000.0]}
        resp = client.post("/pre_condition", json=payload, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["dispatch_kw"] == pytest.approx(0.0)

    def test_dispatches_for_severe_ramp_at_low_soc(self, client):
        """A severe spike with low SoC should trigger a max-rate pre-charge."""
        from vpp.agents.battery_manager import bam_service
        bam_service.current_soc_kwh = bam_service.capacity_kwh * 0.30  # 30% — below 40% threshold
        payload = {
            "predicted_load_curve": [200000.0, 300000.0, 500000.0, 420000.0]
        }
        resp = client.post("/pre_condition", json=payload, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["dispatch_kw"] == pytest.approx(bam_service.max_dispatch_kw)

    def test_no_dispatch_if_soc_already_high(self, client):
        """Even with a severe ramp, no pre-condition if SoC is already adequate (≥ 40%)."""
        from vpp.agents.battery_manager import bam_service
        bam_service.current_soc_kwh = bam_service.capacity_kwh * 0.60  # 60% — above threshold
        payload = {
            "predicted_load_curve": [200000.0, 300000.0, 500000.0, 420000.0]
        }
        resp = client.post("/pre_condition", json=payload, headers=AUTH)
        assert resp.json()["dispatch_kw"] == pytest.approx(0.0)

    def test_empty_curve_returns_zero(self, client):
        """An empty prediction list should safely return 0."""
        payload = {"predicted_load_curve": []}
        resp = client.post("/pre_condition", json=payload, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["dispatch_kw"] == pytest.approx(0.0)
