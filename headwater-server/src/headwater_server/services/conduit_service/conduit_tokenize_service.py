from __future__ import annotations
from headwater_api.classes import TokenizationRequest, TokenizationResponse
import logging

logger = logging.getLogger(__name__)


async def conduit_tokenize_service(request: TokenizationRequest) -> TokenizationResponse:
    model = request.model
    text = request.text

    logger.info(f"Processing tokenization query for model: {model}")
    from conduit.core.model.model_async import ModelAsync

    model_obj = ModelAsync(model)
    token_count = await model_obj.tokenize(text)
    return TokenizationResponse(model=model, input_text=text, token_count=token_count)
