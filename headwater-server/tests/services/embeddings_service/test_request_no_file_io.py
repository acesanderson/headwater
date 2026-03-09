from __future__ import annotations
from unittest.mock import patch, MagicMock
from headwater_api.classes import EmbeddingsRequest, ChromaBatch


def test_embeddings_request_no_file_io():
    mock_open = MagicMock(side_effect=AssertionError("File I/O must not occur during validation"))
    with patch("builtins.open", mock_open):
        req = EmbeddingsRequest(
            model="some-model/v1",
            batch=ChromaBatch(ids=["1"], documents=["hello"]),
            task=None,
            prompt=None,
        )
    assert req.model == "some-model/v1"
