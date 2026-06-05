from pydantic import BaseModel, Field

# Current production model. 384d, 256-token sequence cap. Source artifact:
# `title \n summary` concat (see embed_batch_siphon_service).
SIPHON_EMBED_MODEL_V1 = "sentence-transformers/all-MiniLM-L6-v2"

# Target model post-migration. 768d, 8K-token sequence cap. Source artifact:
# the HyDE-shaped description column (see Phase R2 in siphon-server/dev/
# retrieval.md). Note: retrieval.md mentions "v2" but headwater currently
# supports v1.5; the discrepancy is intentional — v1.5 is what's actually
# downloadable + indexed in the EmbeddingModel registry. Bump to v2 later
# if/when it lands in headwater's _TRUST_REMOTE_CODE_MODELS.
SIPHON_EMBED_MODEL_V2 = "nomic-ai/nomic-embed-text-v1.5"

# The live default. Flip this to SIPHON_EMBED_MODEL_V2 once:
#   1. All rows have HyDE-shaped descriptions (item #2 re-enrichment done).
#   2. The destructive embedding-dim migration has run (vector(384) -> vector(768)).
#   3. siphon-server/database/postgres/models.py:EMBED_DIM is bumped to 768.
# The embed_batch_siphon_service.py branches on this name to pick the source
# artifact, so a single flip switches the whole pipeline atomically.
SIPHON_EMBED_MODEL = SIPHON_EMBED_MODEL_V1


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
