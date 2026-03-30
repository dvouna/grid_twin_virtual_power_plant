import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import BaseModel

from vpp.agents.battery_manager import INFLUX_URL

logger = logging.getLogger(__name__)

# InfluxDB connection details (shared with the rest of the VPP stack)
INFLUX_CLOUD_URL = os.getenv("INFLUX_CLOUD_URL")
INFLUX_CLOUD_TOKEN = os.getenv("INFLUX_CLOUD_TOKEN")
INFLUX_CLOUD_ORG = os.getenv("INFLUX_CLOUD_ORG")
INFLUX_CLOUD_BUCKET = os.getenv("INFLUX_CLOUD_BUCKET")


class BatteryManagementAgent:
    """
    Battery Asset Management (BAM) Agent.
    Acts as a central coordinator, gatekeeping dispatch requests from
    ArbitrageTrader and GridResponseActor to protect the physical asset.
    """

    def __init__(self, capacity_kwh: float = 10000.0, max_c_rate: float = 1.0, base_wear_cost_per_kwh: float = 0.015):
        """
        Initialize the BAM Agent.

        Args:
            capacity_kwh: Total energy capacity of the battery in Kilowatt-hours (kWh).
            max_c_rate: The maximum rate of charge/discharge relative to its capacity.
                        (e.g., 1.0 C-Rate on a 10MWh battery = 10000kW max dispatch).
            base_wear_cost_per_kwh: Base estimated cost of cell degradation per kWh cycled ($/kWh).
        """
        self.capacity_kwh = capacity_kwh
        self.max_c_rate = max_c_rate
        self.base_wear_cost_per_kwh = base_wear_cost_per_kwh

        # Concurrency protection
        self.lock = threading.Lock()

        # Internal state — will be overwritten by _restore_state() if prior state exists
        self.current_soc_kwh = capacity_kwh * 0.50  # Default: start at 50% SoC
        self.max_dispatch_kw = capacity_kwh * max_c_rate

    # A1: State Persistence helpers
    def _restore_state(self) -> None:
        """
        On startup, query InfluxDB for the latest persisted SoC and restore it.
        Falls back to the 50% default if no prior record exists.
        """
        try:
            client = InfluxDBClient(url=INFLUX_CLOUD_URL, token=INFLUX_CLOUD_TOKEN, org=INFLUX_CLOUD_ORG)
            query = (
                f'from(bucket: "{INFLUX_CLOUD_BUCKET}")'
                f" |> range(start: -30d)"
                f' |> filter(fn: (r) => r["_measurement"] == "bam_state")'
                f' |> filter(fn: (r) => r["_field"] == "soc_kwh")'
                f" |> last()"
            )
            tables = client.query_api().query(query)
            for table in tables:
                for record in table.records:
                    restored = float(record.get_value())
                    # Clamp to physical limits before trusting the stored value
                    self.current_soc_kwh = max(0.0, min(self.capacity_kwh, restored))
                    logger.info(
                        f"BAM: Restored SoC from InfluxDB → {self.current_soc_kwh:.2f} kWh ({self.soc_percentage * 100:.1f}%)"
                    )
                    return
            logger.warning("BAM: No prior SoC record found in InfluxDB. Starting at 50%.")
        except Exception as e:
            logger.error(f"BAM: State restore failed ({e}). Using 50% default.")
        finally:
            client.close()

    def _persist_state(self) -> None:
        """
        Write the current SoC to InfluxDB so it can be restored on next startup.
        Called after every approved dispatch.
        """
        try:
            client = InfluxDBClient(url=INFLUX_CLOUD_URL, token=INFLUX_CLOUD_TOKEN, org=INFLUX_CLOUD_ORG)
            point = Point("bam_state").field("soc_kwh", self.current_soc_kwh).field("soc_pct", self.soc_percentage)
            client.write_api(write_options=SYNCHRONOUS).write(
                bucket=INFLUX_CLOUD_BUCKET, org=INFLUX_CLOUD_ORG, record=point
            )
        except Exception as e:
            logger.error(f"BAM: State persist failed ({e}). SoC in memory is still correct.")
        finally:
            client.close()

    # A2: Dispatch telemetry
    def _write_dispatch_log(
        self,
        agent_name: str,
        requested_kw: float,
        approved_kw: float,
        status: str,
    ) -> None:
        """
        Push an authoritative dispatch record to InfluxDB from the BAM side.
        This gives a single, canonical audit trail independent of what the actors log.
        """
        try:
            client = InfluxDBClient(url=INFLUX_CLOUD_URL, token=INFLUX_CLOUD_TOKEN, org=INFLUX_CLOUD_ORG)
            point = (
                Point("bam_dispatch_log")
                .tag("agent_name", agent_name)
                .tag("status", status)
                .field("requested_kw", requested_kw)
                .field("approved_kw", approved_kw)
                .field("soc_kwh", self.current_soc_kwh)
                .field("soc_pct", self.soc_percentage)
            )
            client.write_api(write_options=SYNCHRONOUS).write(
                bucket=INFLUX_CLOUD_BUCKET, org=INFLUX_CLOUD_ORG, record=point
            )
        except Exception as e:
            logger.error(f"BAM: Dispatch log write failed ({e}).")
        finally:
            client.close()

    @property
    def soc_percentage(self) -> float:
        """Returns the current State of Charge (SoC) as a percentage (0.0 to 1.0)."""
        return self.current_soc_kwh / self.capacity_kwh

    def _calculate_penalty_factor(self, soc_pct: float) -> float:
        """
        Calculates a degradation penalty factor based on how extreme the SoC is.
        Operating near 0% or 100% causes exponential wear on Lithium-ion cells.
        """
        if soc_pct < 0.10 or soc_pct > 0.90:
            return 3.0  # 3x penalty in the danger zones
        elif soc_pct < 0.20 or soc_pct > 0.80:
            return 1.5  # 1.5x penalty near the edges
        return 1.0  # Base wear in the healthy middle

    def _calculate_degradation_cost(self, kw_requested: float, duration_hours: float) -> float:
        """
        Calculates the financial cost of degradation for a proposed dispatch.

        Args:
            kw_requested: The absolute power requested in Kilowatts (kW).
            duration_hours: The duration of the dispatch in hours.

        Returns:
            The degradation cost in dollars ($).
        """
        energy_kwh = abs(kw_requested) * duration_hours
        penalty = self._calculate_penalty_factor(self.soc_percentage)
        return energy_kwh * self.base_wear_cost_per_kwh * penalty

    def evaluate_request(
        self, agent_name: str, requested_kw: float, duration_hours: float = 5 / 60, expected_revenue: float = 0.0
    ) -> float:
        """
        The central gatekeeper method. Agents submit dispatch requests here.
        Positive kW implies CHARGING. Negative kW implies DISCHARGING.

        Args:
            agent_name: Name of the requesting agent (e.g., 'ArbitrageTrader').
            requested_kw: Requested dispatch power in Kilowatts (kW).
            duration_hours: Expected duration of the dispatch (default 5 minutes).
            expected_revenue: The anticipated profit context from financial trades ($).

        Returns:
            approved_kw: The actual kW cleared for dispatch (scaled or 0 if vetoed).
        """
        with self.lock:
            # 1. C-Rate Scaling (Safety Constraint)
            # Never exceed the physical limits of the inverter / battery telemetry.
            approved_kw = max(-self.max_dispatch_kw, min(self.max_dispatch_kw, requested_kw))

        if approved_kw != requested_kw:
            logger.warning(
                f"BAM Agent: Scaled {agent_name} request of {requested_kw:.2f} kW to {approved_kw:.2f} kW due to {self.max_c_rate} C-Rate limit."
            )

        # 2. State of Charge Constraint (0% / 100% boundary)
        energy_delta_kwh = approved_kw * duration_hours
        projected_soc_kwh = self.current_soc_kwh + energy_delta_kwh
        projected_soc_pct = projected_soc_kwh / self.capacity_kwh

        # If the dispatch pushes us out of bounds, scale it to exactly hit the boundary
        if projected_soc_pct <= 0.0:
            # We can only discharge what is remaining
            approved_kw = -self.current_soc_kwh / duration_hours
            logger.warning(f"BAM Agent: Scaled {agent_name} request to {approved_kw:.2f} kW to prevent 0% SoC.")

        elif projected_soc_pct >= 1.0:
            # We can only charge the remaining headroom
            headroom_kwh = self.capacity_kwh - self.current_soc_kwh
            approved_kw = headroom_kwh / duration_hours
            logger.warning(f"BAM Agent: Scaled {agent_name} request to {approved_kw:.2f} kW to prevent 100% SoC.")

        # 3. Degradation & Economic Veto (Trader only, when expected revenue is provided)
        if expected_revenue > 0.0:
            cost = self._calculate_degradation_cost(approved_kw, duration_hours)
            if expected_revenue < cost:
                logger.info(
                    f"BAM Agent VETO: {agent_name} trade profit (${expected_revenue:.2f}) is lower than projected degradation cost (${cost:.2f}). Rejecting dispatch."
                )
                return 0.0

        # Update official state — always runs for any approved, non-vetoed dispatch
        self.current_soc_kwh += approved_kw * duration_hours

        # A1: Persist new SoC so a restart can recover it
        self._persist_state()

        # Determine status label for the telemetry log
        if approved_kw == 0.0:
            log_status = "DENIED"
        elif approved_kw != requested_kw:
            log_status = "SCALED"
        else:
            log_status = "APPROVED"

        # A2: Write authoritative dispatch record to InfluxDB
        self._write_dispatch_log(agent_name, requested_kw, approved_kw, log_status)

        return approved_kw

    def pre_condition(self, predicted_load_curve: list[float], current_price: float = 0.0) -> float:
        """
        AI Integration: Uses XGBoost predictions to preemptively act.

        Args:
            predicted_load_curve: A list of predicted Net Load values (kW) for the upcoming intervals.
            current_price: Current market price context.

        Returns:
            dispatch_kw: Autonomous dispatch command generated by the BAM agent itself.
        """
        # Example pre-conditioning placeholder logic
        if not predicted_load_curve:
            return 0.0

        peak_predicted_load = max(predicted_load_curve)

        # If a massive load ramp is coming and we are low on charge, force a charge cycle now
        # Assuming peak load above 400MW (400,000 kW) is severe
        if peak_predicted_load > 400000.0 and self.soc_percentage < 0.40:
            logger.info("BAM Agent Pre-Conditioning: Severe load predicted. Pre-charging at Maximum C-Rate.")
            # Request maximum charge from the internal gatekeeper (pass expected_revenue=0 to bypass economic checks since safety takes precedence)
            return self.evaluate_request(agent_name="BAM_PreConditioner", requested_kw=self.max_dispatch_kw)

        return 0.0


# --- FastAPI Microservice Implementation ---
# A1: Lifespan handler — restores persisted SoC from InfluxDB before serving traffic
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("BAM Service starting — restoring state from InfluxDB...")
    bam_service._restore_state()
    yield
    logger.info("BAM Service shutting down.")


# C2: Physical battery parameters driven by environment variables.
# Override at deployment time via Cloud Run / docker-compose env vars
# without requiring any code changes.
bam_service = BatteryManagementAgent(
    capacity_kwh=float(os.getenv("BAM_CAPACITY_KWH", 100000.0)),
    max_c_rate=float(os.getenv("BAM_MAX_C_RATE", 1.0)),
    base_wear_cost_per_kwh=float(os.getenv("BAM_WEAR_COST", 0.015)),
)
app = FastAPI(title="BAM Service API", description="Battery Asset Management Microservice", lifespan=lifespan)


class DispatchRequest(BaseModel):
    agent_name: str
    requested_kw: float
    duration_hours: float = 5 / 60
    expected_revenue_per_kwh: float = 0.0


class DispatchResponse(BaseModel):
    approved_kw: float
    current_soc_kwh: float
    status: str


class PreConditionRequest(BaseModel):
    predicted_load_curve: list[float]
    current_price: float = 0.0


# D1: API Key Authentication
# _api_key_header declares the expected header name for OpenAPI docs.
# NOTE: We intentionally do NOT cache os.getenv("BAM_API_KEY") at module level
# because that value would be frozen at import time — breaking test isolation
# when the test suite sets os.environ["BAM_API_KEY"] after the module is first
# imported by another test file.
_api_key_header = APIKeyHeader(name="X-BAM-API-Key", auto_error=False)


def _verify_api_key(api_key: str = Security(_api_key_header)):
    # Read dynamically so env-var changes (e.g. in tests) are always respected.
    expected_key = os.getenv("BAM_API_KEY")
    if not expected_key:
        logger.warning("BAM_API_KEY is not set — API authentication is DISABLED. Set this env var in production.")
        return
    if api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing BAM API key.",
        )


@app.post("/dispatch", response_model=DispatchResponse, dependencies=[Depends(_verify_api_key)])
def request_dispatch(req: DispatchRequest):
    approved_kw = bam_service.evaluate_request(
        agent_name=req.agent_name,
        requested_kw=req.requested_kw,
        duration_hours=req.duration_hours,
        expected_revenue=req.expected_revenue_per_kwh,
    )

    status = "APPROVED"
    if approved_kw == 0.0 and req.requested_kw != 0.0:
        status = "DENIED"
    elif approved_kw != req.requested_kw:
        status = "SCALED"

    return DispatchResponse(approved_kw=approved_kw, current_soc_kwh=bam_service.current_soc_kwh, status=status)


@app.post("/pre_condition", dependencies=[Depends(_verify_api_key)])
def request_pre_condition(req: PreConditionRequest):
    dispatch_kw = bam_service.pre_condition(
        predicted_load_curve=req.predicted_load_curve, current_price=req.current_price
    )
    return {"dispatch_kw": dispatch_kw}


@app.get("/state")
def get_state():
    return {
        "current_soc_kwh": bam_service.current_soc_kwh,
        "soc_percentage": bam_service.soc_percentage,
        "capacity_kwh": bam_service.capacity_kwh,
        "max_dispatch_kw": bam_service.max_dispatch_kw,
    }


if __name__ == "__main__":
    logger.info("Starting Battery Management Microservice on port 8000...")
    # nosec B104 — binding to all interfaces is intentional; this service runs
    # inside a container where 0.0.0.0 is required for Cloud Run ingress.
    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec B104
