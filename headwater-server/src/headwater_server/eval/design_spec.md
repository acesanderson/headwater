## Simplified LLM-as-Judge Evaluation Framework

### Core Design Philosophy
**"Gemini vs. Local Model Showdown"** - Use your existing Gemini-generated summaries as ground truth, then have an LLM judge compare local model outputs against them.

### Test Data Pipeline
```pseudocode
test_cases = []
for processed_content in your_existing_cache:
    if processed_content.has_gemini_summary():
        test_cases.append({
            "content": processed_content.context,
            "length": len(processed_content.context.split()),
            "ground_truth": processed_content.summary,
            "content_type": processed_content.sourcetype
        })

# Bucket by length for context window testing
buckets = {
    "short": [cases where length < 1000],
    "medium": [cases where 1000 <= length < 5000], 
    "long": [cases where 5000 <= length < 15000],
    "very_long": [cases where length >= 15000]
}
```

### Evaluation Loop
```pseudocode
for model in local_models:
    for bucket_name, test_cases in buckets:
        for test_case in random_sample(test_cases, n=10):
            
            # Generate summary with local model
            local_summary = generate_summary(model, test_case.content)
            
            # LLM-as-Judge comparison
            judgment = judge_model.compare(
                original_content=test_case.content,
                reference_summary=test_case.ground_truth,  # Gemini
                candidate_summary=local_summary,           # Local model
                criteria=["accuracy", "completeness", "style_match"]
            )
            
            record_result(model, bucket_name, judgment)
```

### LLM-as-Judge Prompt Design
```pseudocode
judge_prompt = """
You are evaluating summary quality. Compare these two summaries of the same content:

REFERENCE (high quality): {gemini_summary}
CANDIDATE (being tested): {local_summary}

Rate the CANDIDATE on:
1. Factual accuracy (0-10): Does it contain correct information?
2. Completeness (0-10): Does it cover the key points?
3. Style consistency (0-10): Similar length and tone to reference?
4. Overall preference (A/B): Which would you prefer to read?

Return scores as: accuracy=X, completeness=Y, style=Z, preference=A/B
"""
```

### Lightweight Metrics
- **Context Window Success Rate**: % of cases where model completes successfully per length bucket
- **Quality Scores**: Average LLM-judge ratings across the three dimensions
- **Preference Win Rate**: How often local model is preferred over Gemini reference
- **Speed**: Tokens/second for each length bucket

### Output Dashboard
```pseudocode
results_table = {
    "model_name": ["llama3.1:8b", "qwen2.5:14b", "codestral:22b"],
    "short_success": [100%, 100%, 100%],
    "long_success": [95%, 100%, 90%],
    "avg_accuracy": [7.2, 8.1, 8.5],
    "preference_rate": [35%, 65%, 78%],
    "speed_tps": [45, 28, 18]
}
```

### Key Benefits of This Approach
- **Zero manual annotation** - leverages your existing processed content
- **Real content diversity** - tests across your actual YouTube/GitHub/PDF variety  
- **Context window stress testing** - automatic binning by length
- **Practical relevance** - directly compares against your current pipeline quality
- **Scalable** - can run on hundreds of examples from your cache

The beauty is it piggybacks on all the work you've already done with Siphon, using your existing cache as both test data and ground truth!

### Action Items

# Task List: LLM-as-Judge Evaluation Framework

## Phase 1: Data Preparation
- [x] **Extract test cases from existing cache**
  - Query your PostgreSQL cache for ProcessedContent with existing synthetic_data
  - Filter for items that have Gemini-generated summaries
  - Export to test dataset format (content + ground_truth_summary + metadata)

- [x] **Create length-based buckets**
  - Implement word count binning logic (short/medium/long/very_long)
  - Sample representative cases from each bucket (aim for 10-20 per bucket)
  - Ensure diversity across content types (YouTube, GitHub, etc.)

## Phase 2: Core Evaluation Infrastructure
- [x] **Build model testing harness**
  - Create function to generate summaries using local Ollama models
  - Add error handling for context window overflows
  - Implement timeout handling for slow models

- [x] **Design LLM-as-Judge prompts**
  - Create comparison prompt template (accuracy/completeness/style/preference)
  - Test prompt with a few manual examples to validate output format
  - Add response parsing to extract numerical scores

- [ ] **Set up judge model** ==Async==
  - Choose judge model (Gemini, Claude, or strong local model)
  - Implement judge query function with structured output parsing
  - Add retry logic for judge API failures

## Phase 3: Benchmark Runner
- [ ] **Create evaluation loop**
  - Iterate through models × buckets × test cases
  - Generate local summaries with timing measurements
  - Run LLM-judge comparisons
  - Store results in structured format

## Phase 4: Results & Analysis
- [ ] **Build results aggregation**
  - Calculate average scores per model per bucket
  - Compute preference win rates
  - Generate performance vs. quality trade-off analysis

- [ ] **Create output dashboard**
  - Simple table/CSV with model rankings
  - Visualization of context window capabilities
  - Speed vs. quality scatter plots

## Phase 5: Integration & Automation
- [ ] **Package as reusable tool**
  - Create CLI script for running benchmarks
  - Add configuration for selecting models to test
  - Make it easy to re-run when new models are released

- [ ] **Connect to your model selection process**
  - Generate recommendations based on results
  - Create "deployment readiness" checklist
  - Document optimal parameters for winning models

## Extra credit: multi-judge comparisons

### Core Structure
Instead of a single judge, create a **Judge Panel** that queries all three models and aggregates their scores:

```pseudocode
class JudgePanel:
    judges = ["gemini-2.5", "claude-opus-4.1", "gpt-5"]
    
    def evaluate_summary(content, reference, candidate):
        scores = {}
        for judge in self.judges:
            individual_score = judge.rate(content, reference, candidate)
            scores[judge] = individual_score
        
        return aggregate_scores(scores)
```

### Aggregation Strategies

**Simple Average**: Mean of all judge scores for each dimension
```pseudocode
final_accuracy = (gemini_acc + claude_acc + gpt_acc) / 3
```

**Weighted Consensus**: Weight judges based on their historical reliability
```pseudocode
weights = {"gemini": 0.4, "claude": 0.35, "gpt": 0.25}
final_accuracy = sum(judge_score * weight for judge, weight in weights)
```

**Agreement Analysis**: Track when judges disagree significantly
```pseudocode
if max(scores) - min(scores) > 3:  # High disagreement
    flag_for_manual_review(test_case)
```

### Benefits
- **Reduced judge bias**: No single model's preferences dominate
- **Higher confidence**: Convergent scores from multiple judges are more trustworthy
- **Disagreement detection**: Cases where judges split reveal edge cases or ambiguous content
- **Robustness**: If one judge API fails, others can continue

### Output Format
```pseudocode
result = {
    "accuracy": {"gemini": 8, "claude": 7, "gpt": 9, "consensus": 8.0},
    "completeness": {"gemini": 6, "claude": 8, "gpt": 7, "consensus": 7.0},
    "agreement_level": "high",  # based on variance
    "recommendation": "strong_candidate"  # if consensus > threshold
}
```

This gives you much more robust evaluation at the cost of 3x API calls per comparison.
