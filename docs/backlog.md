# Headwater Backlog

Entries are written for an agent reader: problem statement, trigger, relevant files/systems, and definition of done.

---

## VRAM Offload Monitor

**Problem:** When a model is loaded on Deepwater or Bywater and overflows VRAM, Ollama silently offloads layers to CPU. This degrades inference speed significantly with no visible signal to the caller. The user wants a structured warning emitted immediately when CPU offload is detected — not an error (since it may be intentional), just instant feedback.

**Triggered by:** Discussion during HeadwaterRouter design (2026-03-30). Deferred because it belongs on the destination server, not the router.

**Relevant systems:**
- `ollama ps` on the destination host — shows loaded models and their processor split (e.g. `70%/30% GPU/CPU`). Not a stable API; parse with care.
- `headwater-server/src/headwater_server/services/conduit_service/` — the conduit service layer is where a post-request hook would live.
- `headwater-server/src/headwater_server/server/logging_config.py` — structured warning should go through the existing logging infrastructure.

**Proposed approach:**
- After each conduit generate request completes, shell out to `ollama ps` and parse the processor column.
- If any loaded model shows CPU offload > 0%, emit a structured `logger.warning(...)` with the model name and offload percentage.
- This is best-effort and non-blocking — do not fail the request.
- Alternative: a background polling loop (e.g. every 30s) rather than per-request. Lower overhead, less immediate.

**Definition of done:**
- A warning appears in headwater-server logs within one request of CPU offload being detected.
- Warning includes: model name, GPU%, CPU%, timestamp.
- No impact on request latency or error behavior.
- Covered by a unit test that mocks `ollama ps` output.
