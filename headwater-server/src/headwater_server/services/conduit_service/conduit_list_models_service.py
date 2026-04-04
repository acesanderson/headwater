from __future__ import annotations

import time


async def conduit_list_models_service() -> dict:
    import httpx

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get("http://localhost:11434/api/tags")
        response.raise_for_status()
        data = response.json()

    model_ids = [m["name"] for m in data.get("models", [])]
    created = int(time.time())

    return {
        "object": "list",
        "data": [
            {"id": model_id, "object": "model", "created": created, "owned_by": "headwater"}
            for model_id in sorted(model_ids)
        ],
    }
