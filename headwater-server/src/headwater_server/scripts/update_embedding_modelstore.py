from __future__ import annotations
import sys


def main() -> None:
    from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore
    if not EmbeddingModelStore._is_consistent():
        print("Embedding model specs are not consistent with registry. Updating...")
        try:
            EmbeddingModelStore.update()
            print("Update complete.")
        except Exception as e:
            print(f"Update failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Embedding model specs are consistent. No update needed.")


if __name__ == "__main__":
    main()
