from pydantic import BaseModel


class EmbedBatchResponse(BaseModel):
    embedded: int
    skipped: int
