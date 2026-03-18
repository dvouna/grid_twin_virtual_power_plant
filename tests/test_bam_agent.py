import pytest

from vpp.agents.battery_manager import BatteryManagementAgent


def test_bam_agent_initialization():
    agent = BatteryManagementAgent(capacity_kwh=10000.0, max_c_rate=1.0, base_wear_cost_per_kwh=0.015)
    assert agent.capacity_kwh == 10000.0
    assert agent.max_c_rate == 1.0
    assert agent.current_soc_kwh == 5000.0  # Starts at 50%
    assert agent.soc_percentage == 0.5


def test_c_rate_limit():
    agent = BatteryManagementAgent(capacity_kwh=10000.0, max_c_rate=1.0)
    # Use a short 5-minute window so the SoC boundary doesn't interfere
    duration = 5 / 60.0
    # Request 20,000kW (2C), should be capped at 10,000kW (1C)
    approved_kw = agent.evaluate_request("GridActor", requested_kw=20000.0, duration_hours=duration)
    assert approved_kw == 10000.0

    # Request -15,000kW (-1.5C), should be capped at -10,000kW (-1C)
    approved_kw_discharge = agent.evaluate_request("GridActor", requested_kw=-15000.0, duration_hours=duration)
    assert approved_kw_discharge == -10000.0


def test_soc_boundaries():
    agent = BatteryManagementAgent(capacity_kwh=10000.0, max_c_rate=1.0)
    agent.current_soc_kwh = 9500.0  # 95% SoC

    # Try to charge 10,000kW for 1 hour
    # Should be limited to the remaining 500kWh headroom
    approved_kw = agent.evaluate_request("GridActor", requested_kw=10000.0, duration_hours=1.0)
    assert approved_kw == 500.0

    agent.current_soc_kwh = 500.0  # 5% SoC
    # Try to discharge 10,000kW for 1 hour
    # Should be limited to the remaining 500kWh
    approved_kw_discharge = agent.evaluate_request("GridActor", requested_kw=-10000.0, duration_hours=1.0)
    assert approved_kw_discharge == -500.0


def test_degradation_veto():
    agent = BatteryManagementAgent(capacity_kwh=10000.0, base_wear_cost_per_kwh=0.015)
    # 5000kW discharge for 1 hour = 5000kWh cycled. Base wear cost = 5000 * $0.015 = $75
    # If expected revenue is only $50, the agent should veto the trade (return 0.0)
    approved_kw = agent.evaluate_request("Trader", requested_kw=-5000.0, duration_hours=1.0, expected_revenue=50.0)
    assert approved_kw == 0.0

    # If expected revenue is $100, the agent should allow the trade
    approved_kw_profitable = agent.evaluate_request(
        "Trader", requested_kw=-5000.0, duration_hours=1.0, expected_revenue=100.0
    )
    assert approved_kw_profitable == -5000.0


def test_pre_conditioning():
    agent = BatteryManagementAgent(capacity_kwh=10000.0, max_c_rate=1.0)
    agent.current_soc_kwh = 2000.0  # 20% SoC, very low

    # AI predicts a massive spike in net load (500MW = 500,000kW)
    predictions = [300000.0, 310000.0, 500000.0, 480000.0]

    # Pre-conditioner should order a max charge (10,000kW)
    dispatch_kw = agent.pre_condition(predictions)
    assert dispatch_kw == 10000.0
