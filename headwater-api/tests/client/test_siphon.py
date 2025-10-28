from headwater_api.client.headwater_client import HeadwaterClient
from headwater_api.classes import (
    SyntheticData,
    SyntheticDataRequest,
)
from siphon.context.classes.text_context import TextContext


def test_siphon_client():
    client = HeadwaterClient()
    file_path = "tests/data/sample.txt"
    file_size = 1024
    mime_type = "text/plain"
    file_extension = ".txt"
    content_created_at = 1625155200
    content_modified_at = 1625241600
    context = """
This is a sample text file used for testing purposes.
It contains multiple lines of text to simulate a real document.
The content is simple and straightforward.
    """
    text_context = TextContext(
        context=context,
        file_path=file_path,
        file_size=file_size,
        mime_type=mime_type,
        file_extension=file_extension,
        content_created_at=content_created_at,
        content_modified_at=content_modified_at,
    )
    request = SyntheticDataRequest(context=text_context, model="cogito:32b")
    synthetic_data = client.siphon.generate_synthetic_data(request)
    assert synthetic_data is not None
    assert isinstance(synthetic_data.title, str)
    print(synthetic_data.title)
    assert isinstance(synthetic_data.description, str)
    print(synthetic_data.description)
    assert isinstance(synthetic_data.summary, str)
    print(synthetic_data.summary)
