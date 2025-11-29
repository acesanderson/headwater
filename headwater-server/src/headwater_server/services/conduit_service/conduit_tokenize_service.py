from headwater_api.classes import TokenizationRequest, TokenizationResponse
import logging

logger = logging.getLogger(__name__)


def conduit_tokenize_service(request: TokenizationRequest) -> TokenizationResponse:
    model = request.model
    text = request.text

    logger.info(f"Processing tokenization query for model: {model}")
    from conduit.sync import Model

    model_obj = Model(model)
    token_count = model_obj.tokenize(text)
    response = TokenizationResponse(
        model=model, input_text=text, token_count=token_count
    )
    return response
