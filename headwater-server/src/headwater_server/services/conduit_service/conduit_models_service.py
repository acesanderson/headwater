from __future__ import annotations


async def conduit_models_service(provider: str | None = None) -> dict:
    from conduit.core.model.models.modelstore import ModelStore

    models = ModelStore.models()
    aliases = ModelStore.aliases()

    if provider is not None:
        if provider not in models:
            known = sorted(models.keys())
            raise ValueError(f"Unknown provider '{provider}'. Known: {known}")
        models = {provider: models[provider]}

    return {
        "providers": sorted(models.keys()),
        "models": models,
        "aliases": aliases,
    }
