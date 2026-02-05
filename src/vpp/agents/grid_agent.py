import asyncio
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Ensure src is in the path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.join(BASE_DIR, "src"))

from vpp.agents.strategies.vpp_default_strategy import VPPDefaultStrategy

class GridAgent:
    """
    Autonomous Grid Agent that orchestrates VPP operations via MCP.
    """
    def __init__(self, server_script=None, strategy=None):
        if server_script is None:
            server_script = os.path.join(BASE_DIR, "src", "vpp", "mcp", "mcp_server.py")
        
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_script],
        )
        self.session = None
        self.strategy = strategy or VPPDefaultStrategy()

    async def start(self):
        """Starts the agent and its thinking loop."""
        try:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    self.session = session
                    await session.initialize()
                    
                    print("="*50)
                    print("🤖 GRID AGENT ONLINE")
                    print("="*50)
                    print(f"Connected to MCP Server: {self.server_params.args[0]}")
                    
                    while True:
                        await self.think()
                        # Sleep for simulation interval
                        await asyncio.sleep(20)
        except Exception as e:
            print(f"❌ Agent Crash: {e}")
            import traceback
            traceback.print_exc()

    async def think(self):
        """The core decision-making cycle."""
        print(f"\n[THINK] {asyncio.get_event_loop().time():.2f}")
        
        try:
            # 1. SENSE
            status = await self.session.read_resource("grid://current-status")
            status_text = status.contents[0].text
            print(f"  📡 Sense: {status_text}")

            # 2. PREDICT
            prediction = await self.session.call_tool("predict_30min_Change", arguments={})
            pred_text = prediction.content[0].text
            print(f"  🔮 Prediction: {pred_text.splitlines()[0]}")

            # 3. ANALYZE (Strategy)
            fs_status = await self.session.call_tool("get_feature_store_status", arguments={})
            fs_text = fs_status.content[0].text
            
            actions = self.strategy.evaluate(status_text, pred_text, fs_text)

            # 4. ACT
            if not actions:
                print("  ⚖ Decision: HOLD (No action required)")
            else:
                for action in actions:
                    print(f"  🎬 Action: Executing {action['tool']}({action['args']})")
                    result = await self.session.call_tool(action['tool'], action['args'])
                    print(f"    └─ Response: {result.content[0].text}")

        except Exception as e:
            print(f"  ⚠ Thinking failed: {e}")

if __name__ == "__main__":
    agent = GridAgent()
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print("\n👋 Agent shutting down.")
