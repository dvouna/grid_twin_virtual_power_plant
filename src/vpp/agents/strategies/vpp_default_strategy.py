import re
from .base_strategy import BaseStrategy

class VPPDefaultStrategy(BaseStrategy):
    """
    Standard strategy that prioritizes grid stability and simple arbitrage.
    """
    def __init__(self, critical_threshold=10000, trade_threshold=2000):
        self.critical_threshold = critical_threshold
        self.trade_threshold = trade_threshold

    def evaluate(self, grid_status: str, prediction: str, fs_status: str) -> list:
        actions = []
        
        # Extract ramp data from prediction text
        # Format: "Predicted Ramp: 8500.00 kW UP"
        match = re.search(r"Predicted Ramp: ([\d.-]+) kW (UP|DOWN)", prediction)
        if not match:
            return actions

        ramp_kw = float(match.group(1))
        direction = match.group(2)
        abs_ramp = abs(ramp_kw)

        # 1. STABILITY LOGIC (Mitigating Large Ramps)
        if abs_ramp >= self.critical_threshold:
            if ramp_kw > 0:
                # Upward ramp -> needs more supply
                actions.append({
                    "tool": "dispatch_asset",
                    "args": {"asset_type": "Gas_Peaker", "power_kw": 50000.0}
                })
            else:
                # Downward ramp -> too much supply/too little load
                actions.append({
                    "tool": "dispatch_asset",
                    "args": {"asset_type": "Battery_Charge", "power_kw": 20000.0}
                })

        # 2. ECONOMIC LOGIC (Arbitrage Charging/Discharging)
        # Simplified: Buy low (surplus), Sell high (shortage)
        if abs_ramp >= self.trade_threshold:
            trade_action = "BUY" if ramp_kw > 0 else "SELL"
            actions.append({
                "tool": "execute_trade",
                "args": {"action": trade_action, "volume_kw": 1000.0}
            })

        return actions
