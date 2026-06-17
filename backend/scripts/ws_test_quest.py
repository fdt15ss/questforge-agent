import asyncio
import json

from websockets.asyncio.client import connect


async def main() -> None:
    uri = "ws://127.0.0.1:18000/ws/agent"

    async with connect(uri) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "agent.request",
                    "request_id": "ws-quest-1",
                    "session_id": "dev-session",
                    "client_id": "portfolio-client",
                    "agent": "quest_generator",
                    "payload": {
                        "sub_agent": "quest_generator.production_quest",
                        "progression": {"stage": "early"},
                        "resources": {"iron_ore": 12, "copper_ore": 5},
                        "recent_events": ["first_factory_started"],
                    },
                }
            )
        )
        response = await websocket.recv()
        print(response)


if __name__ == "__main__":
    asyncio.run(main())
