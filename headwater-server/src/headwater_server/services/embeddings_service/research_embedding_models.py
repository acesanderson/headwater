from __future__ import annotations
import logging
from conduit.sync import Conduit, GenerationParams, ConduitOptions, Verbosity
from conduit.core.prompt.prompt import Prompt
from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider

logger = logging.getLogger(__name__)

_RESEARCH_PROMPT = """
You are an assistant providing factual technical specifications for embedding models.

<provider>
{{ provider }}
</provider>

<model>
{{ model }}
</model>

Return an EmbeddingModelSpec object with accurate values for these informational fields only:
- description (50-80 words, factual, no promotional language)
- embedding_dim (integer output vector size, or null if unknown)
- max_seq_length (integer max input tokens, or null if unknown)
- multilingual (true if model supports non-English text)
- parameter_count (string like "110m", "7b", or null if unknown)

Set these fields exactly as written — do not change them:
- prompt_required: false
- valid_prefixes: null
- prompt_unsupported: false
- task_map: null
- model: {{ model }}
- provider: {{ provider }}
""".strip()


def get_embedding_spec(model: str, provider: str) -> EmbeddingModelSpec:
    params = GenerationParams(
        model="sonar-pro",
        response_model=EmbeddingModelSpec,
        output_type="structured_response",
    )
    prompt = Prompt(_RESEARCH_PROMPT)
    options = ConduitOptions(project_name="headwater", verbosity=Verbosity.PROGRESS)
    conduit = Conduit(prompt=prompt, params=params, options=options)
    response = conduit.run(input_variables={"model": model, "provider": provider})
    spec: EmbeddingModelSpec = response.last.parsed
    # Always override model and provider fields — never trust Perplexity's output for these
    return EmbeddingModelSpec(**{
        **spec.model_dump(),
        "model": model,
        "provider": EmbeddingProvider(provider),
        "prompt_required": False,
        "valid_prefixes": None,
        "prompt_unsupported": False,
        "task_map": None,
    })


def create_embedding_spec(model: str, provider: str) -> None:
    from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
        add_embedding_spec,
        in_db,
    )
    if in_db(model):
        logger.warning(f"Spec for '{model}' already in DB — skipping.")
        return
    logger.info(f"Researching spec for {model} ({provider})...")
    spec = get_embedding_spec(model, provider)
    add_embedding_spec(spec)
    logger.info(f"Spec for {model} written to DB.")
