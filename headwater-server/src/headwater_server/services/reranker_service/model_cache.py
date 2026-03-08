from __future__ import annotations
import logging
import os
import threading
from rerankers import Reranker

logger = logging.getLogger(__name__)

_cache: dict[str, Reranker] = {}
_lock = threading.Lock()

_METADATA_KEYS = {"output_type", "api_key_env"}


def get_reranker(resolved_name: str, model_config: dict) -> Reranker:
    if resolved_name not in _cache:
        with _lock:
            if resolved_name not in _cache:
                kwargs = {k: v for k, v in model_config.items() if k not in _METADATA_KEYS}
                if "api_key_env" in model_config:
                    kwargs["api_key"] = os.getenv(model_config["api_key_env"])
                logger.info("loading model: %s", resolved_name)
                _cache[resolved_name] = Reranker(resolved_name, verbose=False, **kwargs)
                logger.info("model loaded and cached: %s", resolved_name)
    else:
        logger.info("cache hit: %s", resolved_name)
    return _cache[resolved_name]
