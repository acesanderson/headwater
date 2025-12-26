"""
Different RAG strategies -- see "late chunking" in particular.

## 1) Traditional chunk-first, then embed each chunk

```python
from sentence_transformers import SentenceTransformer

def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    chunks = []
    i = 0
    while i < len(text):
        j = min(len(text), i + max_chars)
        chunks.append(text[i:j])
        i = max(i + max_chars - overlap, j)  # avoid infinite loop at end
    return chunks

text = open("doc.txt", "r", encoding="utf-8").read()

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

chunks = chunk_text(text)
chunk_embeddings = model.encode(chunks, normalize_embeddings=True)  # shape: (num_chunks, dim)

# Now you store chunk_embeddings in a vector DB, with chunk text as payload.
print(chunk_embeddings.shape)
```

What’s happening: each chunk is encoded **independently**, so it can’t “see” other chunks.

---

## 2) Late chunking: embed the whole doc once, then pool token embeddings into chunk vectors

This version uses `transformers` directly so it works reliably even if your SentenceTransformers build doesn’t expose token embeddings.

```python
import torch
from transformers import AutoModel
from transformers import AutoTokenizer

def chunk_ranges_by_chars(text: str, max_chars: int = 1200, overlap: int = 200) -> list[tuple[int, int]]:
    ranges = []
    i = 0
    while i < len(text):
        j = min(len(text), i + max_chars)
        ranges.append((i, j))
        i = max(i + max_chars - overlap, j)
    return ranges

text = open("doc.txt", "r", encoding="utf-8").read()

model_name = "sentence-transformers/all-MiniLM-L6-v2"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModel.from_pretrained(model_name)
model.eval()

# 1) Tokenize the entire document (or as much as fits)
enc = tokenizer(
    text,
    return_tensors="pt",
    return_offsets_mapping=True,   # lets us map tokens back to character spans
    truncation=True,               # IMPORTANT: late chunking only applies to what fits
    max_length=tokenizer.model_max_length,
)

offsets = enc.pop("offset_mapping")[0]        # shape: (seq_len, 2), character offsets per token
attention_mask = enc["attention_mask"][0]     # shape: (seq_len,)

with torch.no_grad():
    out = model(**enc)
token_emb = out.last_hidden_state[0]          # shape: (seq_len, hidden_dim)

# 2) Define chunk boundaries in character space, then pool token embeddings per chunk
ranges = chunk_ranges_by_chars(text)

chunk_vecs = []
for start_char, end_char in ranges:
    # tokens whose character span overlaps the chunk span
    token_idxs = [
        i for i, (a, b) in enumerate(offsets.tolist())
        if (b > start_char) and (a < end_char) and (attention_mask[i].item() == 1)
    ]
    if not token_idxs:
        continue

    v = token_emb[token_idxs].mean(dim=0)     # mean pooling over tokens
    v = torch.nn.functional.normalize(v, dim=0)
    chunk_vecs.append(v)

chunk_embeddings = torch.stack(chunk_vecs, dim=0)  # shape: (num_chunks, hidden_dim)
print(chunk_embeddings.shape)
```

What’s happening: the model processes the **whole document once**, producing token embeddings that reflect cross-document context; you then create chunk embeddings by **averaging** the tokens that fall inside each chunk span.
"""
