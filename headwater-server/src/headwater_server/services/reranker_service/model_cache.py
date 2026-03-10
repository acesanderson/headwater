from __future__ import annotations
import logging
import os
import threading
import torch
from rerankers import Reranker

logger = logging.getLogger(__name__)

_cache: dict[str, Reranker] = {}
_lock = threading.Lock()

_METADATA_KEYS = {"output_type", "api_key_env"}


def get_reranker(resolved_name: str, model_config: dict) -> Reranker:
    if resolved_name not in _cache:
        with _lock:
            if resolved_name not in _cache:
                # Evict all other models before loading the new one.
                # Drop references only — do NOT call .cpu() as that races
                # with any in-flight inference still running in the executor.
                # CUDA memory is freed once refcount drops to zero.
                for name in list(_cache.keys()):
                    logger.info("evicting reranker model from GPU: %s", name)
                    del _cache[name]
                torch.cuda.empty_cache()

                kwargs = {k: v for k, v in model_config.items() if k not in _METADATA_KEYS}
                if "api_key_env" in model_config:
                    kwargs["api_key"] = os.getenv(model_config["api_key_env"])
                logger.info("loading model: %s", resolved_name)
                try:
                    _cache[resolved_name] = Reranker(resolved_name, verbose=False, **kwargs)
                except Exception as e:
                    logger.error("Failed to instantiate Reranker '%s': %s", resolved_name, e)
                    raise
                logger.info("model loaded and cached: %s", resolved_name)
    else:
        logger.info("cache hit: %s", resolved_name)
    return _cache[resolved_name]
