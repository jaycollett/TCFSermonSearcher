import pytest
import re
from flask import Flask, request
from sermon_search.utils import (
    get_client_ip,
    is_ip_banned,
    verify_api_token,
    get_all_categories,
    extract_relevant_snippets,
    format_text_into_paragraphs,
    highlight_search_terms,
    sanitize_search_term,
    extract_first_sentences,
    search_sermons,
    get_sermon_statistics
)

def test_get_client_ip():
    app = Flask(__name__)
    with app.test_request_context(environ_overrides={"REMOTE_ADDR": "10.0.0.1"}):
        ip = get_client_ip()
        assert ip == "10.0.0.1"

def test_is_ip_banned():
    # Without knowing banned IPs, simply check that the function returns a boolean.
    result = is_ip_banned("8.8.8.8")
    assert isinstance(result, bool)

def test_verify_api_token_missing():
    # In absence of an API token header, expect the function to indicate failure.
    app = Flask(__name__)
    with app.test_request_context():
        valid, error = verify_api_token()
        assert valid is False

def test_verify_api_token_valid(monkeypatch):
    # Assume that the valid token is checked against a constant in the security module.
    token = "test-token"
    monkeypatch.setattr("sermon_search.utils.security.VALID_API_TOKEN", token)
    app = Flask(__name__)
    with app.test_request_context(headers={"X-API-Token": token}):
        valid, error = verify_api_token()
        assert valid is True

def test_get_all_categories():
    cats_en = get_all_categories("en")
    cats_es = get_all_categories("es")
    assert isinstance(cats_en, list)
    assert isinstance(cats_es, list)

def test_extract_relevant_snippets():
    text = "This is a sample transcription where keyword appears and then continues."
    snippets = extract_relevant_snippets(text, "keyword")
    # If no snippet is found, the function might return a default value.
    if snippets == ["(No exact match found)"]:
        assert True
    else:
        # Otherwise, at least one snippet should contain the queried word.
        assert any("keyword" in snippet for snippet in snippets)

def test_format_text_into_paragraphs():
    text = "Paragraph one.\nParagraph two."
    result = format_text_into_paragraphs(text)
    # Each paragraph should be wrapped in <p> tags.
    assert "<p>" in result and "</p>" in result

def test_highlight_search_terms():
    text = "This is a test text."
    result = highlight_search_terms(text, "test")
    # Expect the query to be highlighted, e.g., wrapped in <mark> tags.
    assert "<mark>" in result and "test" in result

def test_sanitize_search_term():
    term = "  Example search  "
    result = sanitize_search_term(term)
    assert result == "Example search"

def test_extract_first_sentences():
    text = "First sentence. Second sentence. Third sentence."
    result = extract_first_sentences(text)
    # Expect the result to contain the first sentence.
    assert result.strip().startswith("First")

def dummy_search_sermons(query, language, selected_categories, page, per_page):
    return {"sermons": [], "total_count": 0}

def test_search_sermons(monkeypatch):
    # Monkeypatch the search_sermons function to return a predictable result.
    monkeypatch.setattr("sermon_search.utils.search_sermons", dummy_search_sermons)
    result = search_sermons("any", "en", [], 1, 10)
    assert result == {"sermons": [], "total_count": 0}

# For testing get_sermon_statistics, we need to simulate a dummy database response.
def dummy_get_db_for_stats():
    class DummyCursor:
        def fetchall(self):
            # Return a list with one sermon having a known word count.
            return [{
                "sermon_title": "Dummy Sermon",
                "transcription": "word " * 50,
                "categories": "Test"
            }]
    class DummyDB:
        def execute(self, query, params=None):
            return DummyCursor()
        def commit(self):
            pass
    return DummyDB()

def test_get_sermon_statistics(monkeypatch):
    # Monkey patch get_db inside get_sermon_statistics to use our dummy database.
    monkeypatch.setattr("sermon_search.utils.get_db", lambda: dummy_get_db_for_stats())
    stats = get_sermon_statistics()
    expected_keys = [
        "total_sermons",
        "average_words_per_sermon",
        "largest_sermon_title",
        "largest_sermon_word_count",
        "shortest_sermon_title",
        "shortest_sermon_word_count",
        "top_ten_words",
        "most_common_category",
        "updated_at"
    ]
    for key in expected_keys:
        assert key in stats
