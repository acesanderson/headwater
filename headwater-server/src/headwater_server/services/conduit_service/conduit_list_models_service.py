from __future__ import annotations

import time


async def conduit_list_models_service() -> dict:
    from conduit.core.model.models.modelstore import ModelStore

    model_ids = ModelStore.local_models()
    created = int(time.time())

    return {
        "object": "list",
        "data": [
            {"id": model_id, "object": "model", "created": created, "owned_by": "headwater"}
            for model_id in sorted(model_ids)
        ],
    }
