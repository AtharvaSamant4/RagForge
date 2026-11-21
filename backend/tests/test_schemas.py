import pytest
from pydantic import ValidationError

from app.schemas import WidgetInput


@pytest.mark.parametrize("origin", ["https://*.example.com", "https://example.com;script-src", "https://example.com path", "https://user:pass@example.com", "https://example.com/path", "javascript:alert(1)", "https://example.com:99999"])
def test_widget_origin_cannot_inject_csp(origin):
    with pytest.raises(ValidationError):
        WidgetInput(enabled=True, allowed_origins=[origin])


def test_widget_origin_normalization():
    widget = WidgetInput(enabled=True, allowed_origins=["https://EXAMPLE.com/", "http://localhost:4000", "http://[::1]:4000"])
    assert widget.allowed_origins == ["https://example.com", "http://localhost:4000", "http://[::1]:4000"]
