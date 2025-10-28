from pydantic import BaseModel, Field


class AccuracyResponse(BaseModel):
    accuracy_score: int = Field(
        description="Score from 1-10 rating factual accuracy compared to gold standard",
        ge=1,
        le=10,
    )
    accuracy_rationale: str = Field(
        description="Comparison of factual correctness against gold standard"
    )


class CompletenessResponse(BaseModel):
    completeness_score: int = Field(
        description="Score from 1-10 rating coverage of key points compared to gold standard",
        ge=1,
        le=10,
    )
    completeness_rationale: str = Field(
        description="Comparison of coverage against gold standard"
    )


class PreferenceResponse(BaseModel):
    preference_score: int = Field(
        description="Score from 1-10 rating preference for candidate vs gold standard",
        ge=1,
        le=10,
    )
    preference_rationale: str = Field(
        description="Explanation of preference based on overall utility"
    )


class StyleResponse(BaseModel):
    style_score: int = Field(
        description="Score from 1-10 rating style and presentation compared to gold standard",
        ge=1,
        le=10,
    )
    style_rationale: str = Field(
        description="Comparison of style and presentation against gold standard"
    )
