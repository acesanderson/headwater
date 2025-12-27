from pydantic import Field, model_validator, BaseModel
from conduit.domain.request.request import GenerationRequest
from conduit.domain.request.generation_params import GenerationParams
from conduit.domain.config.conduit_options import ConduitOptions


class BatchRequest(BaseModel):
    """
    BatchRequest extends ConduitRequest to allow for multiple prompt strings or input variables.
    This is useful for processing multiple requests in a single API call.
    """

    # Batch-specific fields
    prompt_strings_list: list[str] = Field(
        default_factory=list,
        description="List of prompt strings for each request. Prompt strings should be fully rendered.",
    )
    input_variables_list: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of input variables for each request. Each dict should match the model's input schema.",
    )
    prompt_str: str | None = Field(
        default=None, description="Single jinja2 string for the request."
    )

    # Standard request fields
    params: GenerationParams
    options: ConduitOptions

    @model_validator(mode="after")
    def _exactly_one(
        self,
    ):
        has_prompts = bool(self.prompt_strings_list)
        has_vars = bool(self.input_variables_list)
        if has_prompts == has_vars:
            raise ValueError(
                "Provide exactly one of 'prompt_strings' or 'input_variables_list'."
            )
        # If input_variables_list is provided, prompt_str should have a value
        if has_vars and not self.prompt_str:
            raise ValueError(
                "If 'input_variables_list' is provided, 'prompt_str' must also be provided."
            )
        return self


class TokenizationRequest(BaseModel):
    """
    TokenizationRequest is used to request tokenization of a given text input
    using a specified model's tokenizer.
    """

    model: str = Field(
        ...,
        description="The model whose tokenizer will be used for tokenization.",
    )
    text: str = Field(
        ...,
        description="The text input to be tokenized.",
    )


__all__ = [
    "GenerationRequest",
    "BatchRequest",
    "TokenizationRequest",
]
