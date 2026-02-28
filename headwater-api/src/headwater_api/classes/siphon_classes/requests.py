from pydantic import BaseModel, Field

SIPHON_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbedBatchRequest(BaseModel):
    uris: list[str] = Field(
        ..., description="URIs of records to embed. Rows with NULL embedding are encoded; others are skipped unless force=True."
    )
    model: str = Field(
        default=SIPHON_EMBED_MODEL,
        description="SentenceTransformers model name. Must match EMBED_DIM in siphon-server models.",
    )
    force: bool = Field(
        default=False,
        description="Re-embed even if embedding already exists.",
    )
