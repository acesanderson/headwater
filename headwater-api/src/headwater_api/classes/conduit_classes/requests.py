from pydantic import Field, model_validator
from conduit.request.request import Request as ConduitRequest
from typing import override


class BatchRequest(ConduitRequest):
    """
    BatchRequest extends ConduitRequest to allow for multiple prompt strings or input variables.
    This is useful for processing multiple requests in a single API call.
    """

    prompt_strings: list[str] = Field(
        default_factory=list,
        description="List of prompt strings for each request. Prompt strings should be fully rendered.",
    )
    input_variables_list: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of input variables for each request. Each dict should match the model's input schema.",
    )
    prompt_str: str | None = Field(
        default=None, description="Single prompt string for the request."
    )

    # Override model_post_init to allow empty messages
    @override
    def model_post_init(self, __context) -> None:
        """
        Post-initialization method to validate and set parameters,
        specifically allowing the 'messages' list to be empty for batch requests.
        """
        # --- Copied from Request.model_post_init ---
        self._validate_model()  # Still need to validate the model exists
        self._set_provider()  # Still need to determine the provider
        self._validate_temperature()  # Still need to validate temperature
        self._set_client_params()  # Still need to validate client_params

        # --- OMITTED the check for empty messages ---
        # if self.messages is None or len(self.messages) == 0:
        #     raise ValueError("Messages cannot be empty. Likely a code error.")

        # Still validate that the provider was set correctly
        if self.provider == "" or self.provider is None:
            raise ValueError(
                "Provider must be set based on the model. Likely a code error."
            )
        # --- End of copied/modified logic ---

        # The existing _exactly_one validator will still run afterwards

    @model_validator(mode="after")
    def _exactly_one(
        self,
    ):
        has_prompts = bool(self.prompt_strings)
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


__all__ = [
    "ConduitRequest",
    "BatchRequest",
]
