from __future__ import annotations
from typing import TYPE_CHECKING
from headwater_client.api.base_async_api import BaseAsyncAPI

if TYPE_CHECKING:
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest


class OpenAICompatAsyncAPI(BaseAsyncAPI):
    async def chat_completions(self, request: OpenAIChatRequest) -> object:
        from openai.types.chat import ChatCompletion
        response = await self._request(
            "POST",
            "/v1/chat/completions",
            json_payload=request.model_dump_json(by_alias=True),
        )
        return ChatCompletion.model_validate_json(response)
