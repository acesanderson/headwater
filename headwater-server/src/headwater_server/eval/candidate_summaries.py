from training import datasets
from pydantic import BaseModel
from Conduit.sync import Model, Prompt, Conduit, ConduitCache
from pathlib import Path

# Set up cache
Model._chain_cache = ConduitCache()

# Load prompt templates from the specified directory
prompts_dir = Path(
    "/home/fishhouses/Brian_Code/siphon-project/src/siphon/prompts/synthetic_data"
)
prompt_files = prompts_dir.glob("*.jinja2")
# Generate a dictionary of prompt strings by sourcetype
prompt_dicts = {}
for pf in prompt_files:
    if "summary" in pf.name:
        sourcetype = pf.name.split("_")[0]
        prompt_str = pf.read_text()
        prompt_dicts[sourcetype] = prompt_str

# Where we will store our candidate summaries
candidate_file = Path(__file__).parent / "candidate_summaries.jsonl"

# Models to add
# Our list of ollama models
ollama_models = Model.models()["ollama"]
# Removal list
removal_list = [
    "gpt-oss:120b",
    "llava:13b",
    "llava:34b",
    "llava:7b",
    "minicpm-v:8b",
    "granite3.2-vision:2b",
    "llama3.3:70b",
    "llama3.3:latest",
    "llama4:latest",
    "llama4:16x17b",
    "qwq:latest",
]
# Remove models from the ollama_models list
for model in removal_list:
    if model in ollama_models:
        ollama_models.remove(model)


# Define the Candidate model to hold the summary data
class Candidate(BaseModel):
    model_str: str
    context: str
    gold_standard: str
    summary: str


# Our function to generate a candidate summary
def generate_candidate_summary(model_str: str, data: dict) -> Candidate:
    # Our constants
    sourcetype: str = data["sourcetype"]
    context: str = data["context"]
    gold_standard: str = data["gold_standard"]
    # Print statements
    print(f"Generating summary for sourcetype: {sourcetype}")
    print(f"Context word count: {len(context.split())}")
    print(f"Gold standard word count: {len(gold_standard.split())}")
    print(f"Using model: {model_str}")
    # Construct our chain
    prompt = Prompt(prompt_dicts[sourcetype.lower()])
    model = Model(model=model_str)
    chain = Conduit(prompt=prompt, model=model)
    response = chain.run(input_variables=data)
    candidate = Candidate(
        model_str=model_str,
        context=context,
        gold_standard=gold_standard,
        summary=str(response.content).strip(),
    )
    return candidate


def generate_candidate_summaries(
    datasets: dict, ollama_models: list
) -> list[Candidate]:
    candidates = []
    for model_str in ollama_models:
        for index, datum in enumerate(datasets.items()):
            wordcount = datum[0]
            data_list = datum[1]
            print(f"Processing wordcount category: {wordcount} with model: {model_str}")
            for index2, data in enumerate(data_list):
                print(f"Processing data index: {index2} of {len(data_list)}")
                candidate = generate_candidate_summary(model_str=model_str, data=data)
                candidates.append(candidate)
    return candidates


if __name__ == "__main__":
    candidate_summaries = generate_candidate_summaries(datasets, ollama_models)
    candidate_file = Path(__file__).parent / "candidate_summaries.jsonl"
    with candidate_file.open("w") as f:
        for candidate in candidate_summaries:
            f.write(candidate.model_dump_json() + "\n")
