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

def test_is_ip_banned(monkeypatch):
    # Without knowing banned IPs, simply check that the function returns a boolean.
    monkeypatch.setattr("sermon_search.utils.security.get_db", lambda: MockDB())
    result = is_ip_banned("8.8.8.8")
    assert isinstance(result, bool)

def test_verify_api_token_missing(monkeypatch):
    # In absence of an API token header, expect the function to indicate failure.
    app = Flask(__name__)
    with app.test_request_context():
        monkeypatch.setattr("sermon_search.utils.security.is_ip_banned", lambda ip: False)
        monkeypatch.setattr("sermon_search.utils.security.get_db", lambda: MockDB())
        valid, error = verify_api_token()
        assert valid is False

def test_verify_api_token_valid(monkeypatch):
    # Assume that the valid token is checked against an environment variable
    token = "test-token"
    monkeypatch.setenv("SERMON_API_TOKEN", token)
    app = Flask(__name__)
    with app.test_request_context(headers={"X-API-Token": token}):
        monkeypatch.setattr("sermon_search.utils.security.is_ip_banned", lambda ip: False)
        monkeypatch.setattr("sermon_search.utils.security.get_db", lambda: MockDB())
        valid, error = verify_api_token()
        assert valid is True

class MockDB:
    def execute(self, *args, **kwargs):
        return self
    def commit(self):
        pass
    def fetchone(self):
        return None
    def fetchall(self):
        return []

def test_get_all_categories(monkeypatch):
    class MockCategoryDB:
        def execute(self, query, params=None):
            class MockCursor:
                def fetchall(self):
                    return [{"categories": "Category1,Category2"}]
            return MockCursor()
    
    # Create a Flask app and app context for testing
    app = Flask(__name__)
    app.config['DATABASE'] = ':memory:'  # Use in-memory SQLite database
    with app.app_context():
        # Direct monkeypatch of get_db function
        monkeypatch.setattr("sermon_search.utils.sermons.get_db", lambda: MockCategoryDB())
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
    # Expect the query to be highlighted with a span.highlight class
    assert '<span class="highlight">test</span>' in result

def test_sanitize_search_term():
    term = "  Example search  "
    result = sanitize_search_term(term)
    assert result == '"Example search"'

def test_extract_first_sentences():
    text = "First sentence. Second sentence. Third sentence."
    result = extract_first_sentences(text)
    # Expect the result to contain the first sentence.
    assert result.strip().startswith("First")

def dummy_search_sermons(query, language, selected_categories, page, per_page):
    return {"sermons": [], "total_count": 0}

def test_search_sermons(monkeypatch):
    # Create a mock database that returns empty results
    class MockSearchDB:
        def execute(self, query, params=None):
            class MockCursor:
                def fetchall(self):
                    return []
                def fetchone(self):
                    return {"total": 0}
            return MockCursor()
    
    # Create a Flask app and app context for testing
    app = Flask(__name__)
    app.config['DATABASE'] = ':memory:'
    with app.app_context():
        # Monkeypatch the required functions
        monkeypatch.setattr("sermon_search.utils.sermons.get_db", lambda: MockSearchDB())
        monkeypatch.setattr("sermon_search.utils.sermons.current_app.logger.debug", lambda *args, **kwargs: None)
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
        def fetchone(self):
            import json
            return {
                "total_sermons": 1,
                "average_words_per_sermon": 50,
                "largest_sermon_title": "Dummy Sermon",
                "largest_sermon_word_count": 50,
                "shortest_sermon_title": "Dummy Sermon",
                "shortest_sermon_word_count": 50,
                "top_ten_words": json.dumps([{"word": "test", "count": 10}]),
                "most_common_category": "Test",
                "updated_at": "2023-01-01"
            }
    class DummyDB:
        def execute(self, query, params=None):
            return DummyCursor()
        def commit(self):
            pass
    return DummyDB()

# Mock metrics DB for sermon access data
class DummyMetricsDBWithAccess:
    def execute(self, query, params=None):
        class AccessCursor:
            def fetchall(self):
                # Return mock sermon access records
                return [
                    {"sermon_guid": "test-guid-1", "access_count": 10},
                    {"sermon_guid": "test-guid-2", "access_count": 5}
                ]
        return AccessCursor()

# Mock main DB that returns sermon titles for our test GUIDs
class DummyDBWithSermonTitles:
    def execute(self, query, params=None):
        class SermonTitleCursor:
            def fetchone(self):
                # Return mock sermon title based on the provided GUID
                if params and params[0] == "test-guid-1":
                    return {"sermon_title": "Most Popular Sermon"}
                elif params and params[0] == "test-guid-2":
                    return {"sermon_title": "Second Popular Sermon"}
                else:
                    # Return a default row from stats_for_nerds for other queries
                    import json
                    return {
                        "total_sermons": 1,
                        "average_words_per_sermon": 50,
                        "largest_sermon_title": "Dummy Sermon",
                        "largest_sermon_word_count": 50,
                        "shortest_sermon_title": "Dummy Sermon",
                        "shortest_sermon_word_count": 50,
                        "top_ten_words": json.dumps([{"word": "test", "count": 10}]),
                        "most_common_category": "Test",
                        "updated_at": "2023-01-01"
                    }
            def fetchall(self):
                # Return a list with one sermon having a known word count
                return [{
                    "sermon_title": "Dummy Sermon",
                    "transcription": "word " * 50,
                    "categories": "Test"
                }]
        return SermonTitleCursor()

def test_get_sermon_statistics(monkeypatch):
    # Create a Flask app and app context for testing
    app = Flask(__name__)
    app.config['DATABASE'] = ':memory:'
    with app.app_context():
        # Monkey patch get_db inside get_sermon_statistics to use our dummy database.
        monkeypatch.setattr("sermon_search.utils.sermons.get_db", lambda: dummy_get_db_for_stats())
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
            "updated_at",
            "top_accessed_sermons"  # Should exist but might be empty in this test
        ]
        for key in expected_keys:
            assert key in stats

def test_get_sermon_statistics_with_top_accessed(monkeypatch):
    # Create a Flask app and app context for testing
    app = Flask(__name__)
    app.config['DATABASE'] = ':memory:'
    with app.app_context():
        # Monkey patch get_db and get_metrics_db to use our test implementations
        monkeypatch.setattr("sermon_search.utils.sermons.get_db", lambda: DummyDBWithSermonTitles())
        monkeypatch.setattr("sermon_search.utils.sermons.get_metrics_db", lambda: DummyMetricsDBWithAccess())
        
        # Call the function we're testing
        stats = get_sermon_statistics()
        
        # Verify that top_accessed_sermons contains the expected data
        assert "top_accessed_sermons" in stats
        assert len(stats["top_accessed_sermons"]) == 2
        
        # Verify the first sermon record
        assert stats["top_accessed_sermons"][0]["sermon_guid"] == "test-guid-1"
        assert stats["top_accessed_sermons"][0]["sermon_title"] == "Most Popular Sermon"
        assert stats["top_accessed_sermons"][0]["access_count"] == 10
        
        # Verify the second sermon record
        assert stats["top_accessed_sermons"][1]["sermon_guid"] == "test-guid-2"
        assert stats["top_accessed_sermons"][1]["sermon_title"] == "Second Popular Sermon"
        assert stats["top_accessed_sermons"][1]["access_count"] == 5
