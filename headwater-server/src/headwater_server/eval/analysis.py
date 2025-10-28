from siphonserver.eval.eval import evaluations_file, Evaluation
from pathlib import Path
import pandas as pd

# Load evaluations from the specified file
evaluations = []
assert evaluations_file.exists(), f"Evaluations file not found: {evaluations_file}"
with evaluations_file.open("r") as f:
    for line in f:
        eval = Evaluation.model_validate_json(line.strip())
        evaluations.append(eval)

print(len(evaluations), "evaluations loaded.")

columns = """
model_str
sourcetype
context
gold_standard
summary
accuracy_score
coherence_score
relevance_score
fluency_score
accuracy_rationale
coherence_rationale
relevance_rationale
fluency_rationale
overall_score
""".strip().split("\n")

# Convert evaluations to a DataFrame
df = pd.DataFrame([eval.model_dump() for eval in evaluations], columns=columns)


# Create a column that identifies one of the following bands:
## 1000 if len(content.split()) < 1000
## 2000 if 1000 <= len(content.split()) < 2000
## 3000 if 2000 <= len(content.split()) < 3000
## 4000 if 3000 <= len(content.split()) < 4000
## 5000 if 4000 <= len(content.split()) < 5000
## 6000 if 5000 <= len(content.split()) < 6000
## 7000 if 6000 <= len(content.split()) < 7000
def length_band(summary: str) -> int:
    length = len(summary.split())
    if length < 1000:
        return 1000
    elif length < 2000:
        return 2000
    elif length < 3000:
        return 3000
    elif length < 4000:
        return 4000
    elif length < 5000:
        return 5000
    elif length < 6000:
        return 6000
    elif length < 7500:
        return 7500
    else:
        return 10000


df["length_band"] = df["context"].apply(length_band)

# Analysis 1: average scores by model and length band
avg_scores = (
    df.groupby(["model_str", "length_band"])[
        [
            "accuracy_score",
            "coherence_score",
            "relevance_score",
            "fluency_score",
            "overall_score",
        ]
    ]
    .mean()
    .reset_index()
)

# Save the average scores to a CSV file
output_file = Path("average_scores_by_model_and_length_band.csv")
avg_scores.to_csv(output_file, index=False)
print(f"Average scores saved to {output_file}")
