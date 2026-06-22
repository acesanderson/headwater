# backwater (embeddings host) — capacity constraints

`routes.yaml` sends `embeddings: backwater`. Backwater runs on **botvinnik**, a laptop-class host with:

- **GPU**: NVIDIA GeForce GTX 1650 Ti Mobile
- **VRAM**: 3.63 GB total
- **Typical free VRAM after nomic loads**: ~1 GB

This is dramatically smaller than alphablue's enterprise-class GPU. The embedding service has to be configured for backwater's envelope, not the upstream model defaults.

## Why this matters

GPU memory at inference time is dominated by **attention**, which is `O(batch × heads × seq_len²)`. Concrete numbers for `nomic-ai/nomic-embed-text-v1.5` (12 heads, fp32 working buffers):

| batch | seq_len | attention memory |
| ---: | ---: | ---: |
| 32 | 2048 | ~6.4 GB → OOM |
| 32 | 1024 | ~1.6 GB |
| 8 | 2048 | ~1.6 GB |
| 8 | 1024 | ~400 MB |
| 8 | 512 | ~100 MB |

The pre-2026-06-21 default (`batch_size=32`, native `max_seq_length=2048`) tries to allocate ~6.4 GB and OOMs immediately on backwater.

## Current settings

In `embedding_model.py`:

- **`_apply_runtime_limits`** caps `_st_model.max_seq_length = 1024` for nomic. Truncates inputs above 1024 tokens. Most stored content (Siphon descriptions, typical Obsidian notes) is well under this.
- **`_nomic_handler`** uses `batch_size=8`. SentenceTransformer's `encode()` chunks any larger payload through this batch size internally.

Together: per forward pass ~400 MB of attention. Comfortable headroom for concurrent callers.

## What this means for callers

**Nothing.** Callers can POST batches of any size to `/conduit/embeddings`. The server chunks internally and returns the full result list. The constraint is invisible from the API.

If you write a new embedding caller, the right behavior is:

- Pick HTTP-payload chunk size for **network efficiency**, not for GPU memory. 64-256 is fine.
- Do not duplicate GPU-memory knowledge in the caller.

If you change the embedding host (e.g., move to a 24 GB GPU), bump `_apply_runtime_limits` and the per-model handler's `batch_size`. Single point of update.

## What gets truncated

`max_seq_length=1024` means inputs longer than 1024 tokens are silently cut to the first 1024. For Siphon's HyDE-shaped descriptions (~130-180 words, ~200 tokens), this is invisible. For Blackglass embedding Obsidian notes, very long notes (>4 pages of dense prose) lose the tail.

If silent truncation becomes a quality problem for a specific consumer, options in order of preference:

1. Pre-chunk caller-side: split long inputs into multiple sub-1024-token segments and embed each.
2. Drop `batch_size` to 4 and bump `max_seq_length` to 2048 in `_apply_runtime_limits`.
3. Move the embedding host to bigger iron.
