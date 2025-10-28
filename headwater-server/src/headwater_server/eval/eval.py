from candidate_summaries import Candidate, candidate_file
from prompts.response_classes import (
    AccuracyResponse,
    CompletenessResponse,
    PreferenceResponse,
    StyleResponse,
)
from Conduit.sync import Model, Prompt, Conduit, Parser
from pathlib import Path
from pydantic import BaseModel


# Grab the prompt files
prompts_dir = Path(__file__).parent / "prompts"
prompt_files = list(prompts_dir.glob("*.jinja2"))
# Generate a dictionary of prompts
prompt_dict = {}
for prompt_file in prompt_files:
    # Extract the prompt name from the file name
    prompt_name = prompt_file.stem
    # Read the prompt file and store it in the dictionary
    prompt_dict[prompt_name] = prompt_file.read_text()

# Load candidate summaries from a JSONL file
candidate_summaries = []
with candidate_file.open("r") as f:
    for line in f:
        candidate_summaries.append(Candidate.model_validate_json(line.strip()))
# Reverse the list to evaluate the most recent candidates first
candidate_summaries.reverse()

# Where to store the evaluations
evaluations_file = Path(__name__).parent / "evaluations.jsonl"


# Our data class
class Evaluation(BaseModel):
    # Metadata
    model_str: str
    sourcetype: str
    context: str
    gold_standard: str
    summary: str

    # Scores
    accuracy_score: int
    coherence_score: int
    relevance_score: int
    fluency_score: int

    # Rationales
    accuracy_rationale: str
    coherence_rationale: str
    relevance_rationale: str
    fluency_rationale: str

    # Overall score (calculated after initialization)
    overall_score: int | None = None

    def model_post_init(self, __context=None):
        # Calculate the overall score as the average of the individual scores
        self.overall_score = (
            self.accuracy_score
            + self.coherence_score
            + self.relevance_score
            + self.fluency_score
        )


# Our orchestration function to evaluate a model
def evaluate_model(candidate: Candidate) -> Evaluation:
    # Metadata
    model_str = candidate.model_str
    context = candidate.context
    gold_standard = candidate.gold_standard
    summary = candidate.summary
    # Create a model instance
    model = Model("flash")
    completeness_response = evaluate_completeness(candidate, model)
    assert isinstance(completeness_response, CompletenessResponse)
    accuracy_response = evaluate_accuracy(candidate, model)
    assert isinstance(accuracy_response, AccuracyResponse)
    style_response = evaluate_style(candidate, model)
    assert isinstance(style_response, StyleResponse)
    preference_response = evaluate_preference(candidate, model)
    assert isinstance(preference_response, PreferenceResponse)
    # Create an Evaluation object
    evaluation = Evaluation(
        model_str=model_str,
        sourcetype="candidate",
        context=context,
        gold_standard=gold_standard,
        summary=summary,
        accuracy_score=accuracy_response.accuracy_score,
        coherence_score=completeness_response.completeness_score,
        relevance_score=style_response.style_score,
        fluency_score=preference_response.preference_score,
        accuracy_rationale=accuracy_response.accuracy_rationale,
        coherence_rationale=completeness_response.completeness_rationale,
        relevance_rationale=style_response.style_rationale,
        fluency_rationale=preference_response.preference_rationale,
    )
    return evaluation


def evaluate_completeness(candidate: Candidate, model: Model) -> CompletenessResponse:
    # Input variables dict
    context = candidate.context
    gold_standard = candidate.gold_standard
    summary = candidate.summary
    input_variables = {
        "context": context,
        "gold_standard": gold_standard,
        "candidate_summary": summary,
    }
    # Build our chain
    prompt = Prompt(prompt_dict["completeness"])
    parser = Parser(CompletenessResponse)
    chain = Conduit(model=model, prompt=prompt, parser=parser)
    response = chain.run(input_variables=input_variables)
    return response.content


def evaluate_accuracy(candidate: Candidate, model: Model) -> AccuracyResponse:
    # Input variables dict
    context = candidate.context
    gold_standard = candidate.gold_standard
    summary = candidate.summary
    input_variables = {
        "context": context,
        "gold_standard": gold_standard,
        "candidate_summary": summary,
    }
    # Build our chain
    prompt = Prompt(prompt_dict["accuracy"])
    parser = Parser(AccuracyResponse)
    chain = Conduit(model=model, prompt=prompt, parser=parser)
    response = chain.run(input_variables=input_variables)
    return response.content


def evaluate_style(candidate: Candidate, model: Model) -> StyleResponse:
    # Input variables dict
    context = candidate.context
    gold_standard = candidate.gold_standard
    summary = candidate.summary
    input_variables = {
        "context": context,
        "gold_standard": gold_standard,
        "candidate_summary": summary,
    }
    # Build our chain
    prompt = Prompt(prompt_dict["style"])
    parser = Parser(StyleResponse)
    chain = Conduit(model=model, prompt=prompt, parser=parser)
    response = chain.run(input_variables=input_variables)
    return response.content


def evaluate_preference(candidate: Candidate, model: Model) -> PreferenceResponse:
    # Input variables dict
    context = candidate.context
    gold_standard = candidate.gold_standard
    summary = candidate.summary
    input_variables = {
        "context": context,
        "gold_standard": gold_standard,
        "candidate_summary": summary,
    }
    # Build our chain
    prompt = Prompt(prompt_dict["preference"])
    parser = Parser(PreferenceResponse)
    chain = Conduit(model=model, prompt=prompt, parser=parser)
    response = chain.run(input_variables=input_variables)
    return response.content


if __name__ == "__main__":
    evaluations = []
    for index, candidate_summary in enumerate(candidate_summaries):
        print(f"Evaluating candidate {index + 1}/{len(candidate_summaries)}")
        evaluation = evaluate_model(candidate_summary)
        evaluations.append(evaluation)

    with evaluations_file.open("w") as f:
        for evaluation in evaluations:
            f.write(evaluation.model_dump_json() + "\n")
