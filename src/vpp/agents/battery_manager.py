import logging

logger = logging.getLogger(__name__)

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
        
        # Internal state tracking
        self.current_soc_kwh = capacity_kwh * 0.50  # Start at 50% SoC
        self.max_dispatch_kw = capacity_kwh * max_c_rate

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
        return 1.0      # Base wear in the healthy middle

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

    def evaluate_request(self, agent_name: str, requested_kw: float, duration_hours: float = 5/60, expected_revenue: float = 0.0) -> float:
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
        # 1. C-Rate Scaling (Safety Constraint)
        # Never exceed the physical limits of the inverter / battery telemetry.
        approved_kw = max(-self.max_dispatch_kw, min(self.max_dispatch_kw, requested_kw))
        
        if approved_kw != requested_kw:
            logger.warning(f"BAM Agent: Scaled {agent_name} request of {requested_kw:.2f} kW to {approved_kw:.2f} kW due to {self.max_c_rate} C-Rate limit.")

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

        # 3. Degradation & Economic Veto (Trader only)
        if expected_revenue > 0.0:
            cost = self._calculate_degradation_cost(approved_kw, duration_hours)
            if expected_revenue < cost:
                logger.info(f"BAM Agent VETO: {agent_name} trade profit (${expected_revenue:.2f}) is lower than projected degradation cost (${cost:.2f}). Rejecting dispatch.")
                return 0.0

        # Update official state (In a real system, this updates via hardware telemetry, but for simulation we track it here)
        self.current_soc_kwh += (approved_kw * duration_hours)
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
