# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27", "rich>=13"]
# ///
"""Fire a potpourri of lightweight requests at Headwater for TUI display testing."""
from __future__ import annotations

import argparse
import random
import time

import httpx
from rich.console import Console

ROUTER = "http://172.16.0.4:8081"

QUERIES = [
    "What is machine learning?",
    "Explain transformer architecture",
    "How does attention work?",
    "Define gradient descent",
    "What is a neural network?",
    "Explain backpropagation",
    "What is overfitting?",
    "Define regularization in ML",
    "What is BERT?",
    "Explain fine-tuning a model",
    "What is RAG?",
    "Describe vector search",
    "What is cosine similarity?",
    "Explain tokenization",
    "What are embeddings?",
]

RERANK_DOCS = [
    "Machine learning is a subset of artificial intelligence.",
    "Deep learning uses neural networks with many layers.",
    "Transformers use self-attention mechanisms.",
    "BERT is a pre-trained language model.",
    "Fine-tuning adapts a pre-trained model to specific tasks.",
    "Overfitting occurs when a model memorizes training data.",
    "Regularization prevents overfitting by adding penalties.",
    "Gradient descent optimizes model parameters iteratively.",
    "Vector search finds nearest neighbors in embedding space.",
    "RAG retrieves relevant documents before generation.",
]

EMBED_MODELS = [
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/all-mpnet-base-v2",
]

TOKENIZE_MODELS = [
    "llama3.2",
    "qwen2.5:14b",
]


def fire_quick_embed(client: httpx.Client, query: str | None = None) -> str:
    q = query or random.choice(QUERIES)
    model = random.choice(EMBED_MODELS)
    r = client.post(
        f"{ROUTER}/conduit/embeddings/quick",
        json={"query": q, "model": model},
        timeout=10.0,
    )
    return f"quick_embed  [{r.status_code}]  {model.split('/')[-1]}"


def fire_rerank(client: httpx.Client, query: str | None = None) -> str:
    q = query or random.choice(QUERIES)
    docs = random.sample(RERANK_DOCS, k=random.randint(3, 6))
    r = client.post(
        f"{ROUTER}/reranker/rerank",
        json={"query": q, "documents": docs, "model_name": "flash", "k": 3},
        timeout=10.0,
    )
    return f"rerank       [{r.status_code}]"


def fire_tokenize(client: httpx.Client, query: str | None = None) -> str:
    text = query or random.choice(QUERIES)
    model = random.choice(TOKENIZE_MODELS)
    r = client.post(
        f"{ROUTER}/conduit/tokenize",
        json={"model": model, "text": text},
        timeout=10.0,
    )
    return f"tokenize     [{r.status_code}]  {model}"


_SHOT_POOL: list[tuple] = [
    (fire_quick_embed, 5),
    (fire_rerank, 2),
    (fire_tokenize, 1),
]
_FNS, _WEIGHTS = zip(*_SHOT_POOL)


def _pick() -> object:
    return random.choices(_FNS, weights=_WEIGHTS, k=1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Blast test requests at Headwater TUI")
    parser.add_argument("--delay", type=float, default=0.4, help="Seconds between requests")
    parser.add_argument("--n", type=int, default=60, help="Total requests to fire")
    parser.add_argument("--burst-prob", type=float, default=0.15, help="Probability of a burst run")
    args = parser.parse_args()

    console = Console()
    console.print(f"[bold]Blasting {args.n} requests at {ROUTER}[/bold]  (delay={args.delay}s, burst_prob={args.burst_prob})")

    fired = 0
    with httpx.Client() as client:
        while fired < args.n:
            if random.random() < args.burst_prob:
                burst_fn = fire_quick_embed
                burst_q = random.choice(QUERIES)
                burst_n = random.randint(3, 7)
                console.print(f"\n[yellow]burst ×{burst_n}  '{burst_q[:40]}'[/yellow]")
                for _ in range(burst_n):
                    try:
                        result = burst_fn(client, burst_q)
                        console.print(f"  [dim]{result}[/dim]")
                    except Exception as exc:
                        console.print(f"  [red]error: {exc}[/red]")
                    time.sleep(args.delay * 0.5)
                    fired += 1
                    if fired >= args.n:
                        break
            else:
                fn = _pick()
                try:
                    result = fn(client)
                    console.print(f"[green]→[/green]  {result}")
                except Exception as exc:
                    console.print(f"[red]error: {exc}[/red]")
                fired += 1
                time.sleep(args.delay)

    console.print(f"\n[bold green]Done. {fired} requests fired.[/bold green]")


if __name__ == "__main__":
    main()
