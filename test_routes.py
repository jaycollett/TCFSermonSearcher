import io
import json
import uuid
import datetime
import pytest

from flask import Response
from sermon_search.app_factory import create_app

# Dummy functions for monkeypatching
def dummy_search_sermons(query, language, selected_categories, page, per_page):
    return {
        "sermons": [{
            "sermon_guid": "dummy-guid",
            "sermon_title": "Dummy Sermon",
            "audiofilename": "dummy.mp3",
            "categories": "Test",
            "transcription": "This is a test transcription with keyword."
        }],
        "total_count": 1
    }

def dummy_get_sermon_by_guid(guid, language):
    return {
        "sermon_guid": guid,
        "sermon_title": "Valid Sermon",
        "transcription": "This is a test transcription."
    }

def dummy_get_ai_content_by_guid(guid):
    return {
        "key_quotes": "Test Quote"
    }

def dummy_format_text_into_paragraphs(text):
    return "<p>" + text + "</p>"

def dummy_highlight_search_terms(text, query):
    return text.replace(query, f"<mark>{query}</mark>")

# Dummy DB classes for various endpoints
class DummyCursor:
    def fetchall(self):
        return []

class DummyDB:
    def execute(self, query, params=None):
        return DummyCursor()
    def commit(self):
        pass

class DummyCursorList:
    def fetchall(self):
        return [{
            "sermon_guid": "dummy-guid",
            "sermon_title": "Dummy Title",
            "transcription": "Dummy transcription.",
            "categories": "Dummy"
        }]

class DummyDBList:
    def execute(self, query, params=None):
        return DummyCursorList()

class DummyDBStats:
    def __init__(self, sermons):
        self.sermons = sermons
        self.operations = []
    def execute(self, query, params=None):
        self.operations.append((query, params))
        class DummyCursor:
            def fetchall(inner_self):
                return self.sermons
        return DummyCursor()
    def commit(self):
        self.operations.append(("commit", None))

def dummy_get_db_stats():
    sermons = [{
        "sermon_title": "Test Sermon",
        "transcription": "word " * 100,
        "categories": "Test"
    }]
    return DummyDBStats(sermons)

def dummy_send_from_directory(directory, filename):
    return Response("dummy file content", mimetype="audio/mpeg")

class DummyDBUpload:
    def execute(self, query, params):
        pass
    def commit(self):
        pass

# Pytest fixtures for app and client
@pytest.fixture
def app():
    app = create_app('testing')
    app.config['TESTING'] = True
    # Set a dummy AUDIOFILES_DIR for testing
    app.config['AUDIOFILES_DIR'] = "/dummy/path"
    return app

@pytest.fixture
def client(app):
    return app.test_client()

# Test index route
def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Welcome" in response.data

# Test set_language route with valid language
def test_set_language_valid(client):
    response = client.post("/set_language", data={"language": "es"})
    assert response.status_code == 302
    cookie = response.headers.get("Set-Cookie", "")
    assert "language=es" in cookie
    # Follow the redirect to verify the final status code is 200
    follow_response = client.get(response.headers['Location'])
    assert follow_response.status_code == 200

# Test set_language route with invalid language (fallback to 'en')
def test_set_language_invalid(client):
    response = client.post("/set_language", data={"language": "fr"})
    assert response.status_code == 302
    cookie = response.headers.get("Set-Cookie", "")
    assert "language=en" in cookie
    follow_response = client.get(response.headers['Location'])
    assert follow_response.status_code == 200

# Test sitemap route
def test_sitemap(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    assert b"<urlset" in response.data

# Test robots.txt route (both lowercase and capitalized)
def test_robots(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.mimetype.startswith("text/plain")
    response2 = client.get("/Robots.txt")
    assert response2.status_code == 200
    assert response2.mimetype.startswith("text/plain")

# Test search route without query (renders search page)
def test_search_no_query(client):
    response = client.get("/search")
    assert response.status_code == 200
    # Check for a form element in the rendered search page
    assert b"<form" in response.data

# Test search route with query using dummy search function
def test_search_with_query(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.search_sermons", dummy_search_sermons)
    response = client.get("/search?q=keyword")
    assert response.status_code == 200
    assert b"Dummy Sermon" in response.data

# Test sermon_detail route for a non-existent sermon (should return 404)
def test_sermon_detail_not_found(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.get_sermon_by_guid", lambda guid, lang: None)
    response = client.get("/sermon/nonexistent")
    assert response.status_code == 404

# Test sermon_detail route for an existing sermon
def test_sermon_detail_found(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.get_sermon_by_guid", dummy_get_sermon_by_guid)
    monkeypatch.setattr("sermon_search.routes.get_ai_content_by_guid", dummy_get_ai_content_by_guid)
    monkeypatch.setattr("sermon_search.routes.format_text_into_paragraphs", dummy_format_text_into_paragraphs)
    monkeypatch.setattr("sermon_search.routes.highlight_search_terms", dummy_highlight_search_terms)
    response = client.get("/sermon/dummy-guid?q=test")
    assert response.status_code == 200
    assert b"Valid Sermon" in response.data

# Test stats route
def test_stats(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.get_sermon_statistics", lambda: {"total_sermons": 123})
    response = client.get("/stats")
    assert response.status_code == 200

# Test sermon_index route
def test_sermon_index(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.get_db", lambda: DummyDB())
    response = client.get("/sermons")
    assert response.status_code == 200

# Test API route to get sermons
def test_get_sermons(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.get_db", lambda: DummyDBList())
    response = client.get("/api/sermons")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert isinstance(data, list)
    assert data[0]["sermon_title"] == "Dummy Title"

# Test audiofiles route using dummy send_from_directory
def test_audiofiles(client, monkeypatch, app):
    monkeypatch.setattr("sermon_search.routes.send_from_directory", dummy_send_from_directory)
    response = client.get("/audiofiles/dummy.mp3")
    assert response.status_code == 200
    assert b"dummy file content" in response.data

# Test update_stats API route with invalid API token
def test_update_stats_invalid_token(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.verify_api_token", lambda: (False, "Invalid token"))
    response = client.post("/api/update_stats")
    assert response.status_code in (401, 403)

# Test update_stats API route with no sermons found
def test_update_stats_no_sermons(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.verify_api_token", lambda: (True, None))
    class DummyDBEmpty:
        def execute(self, query, params=None):
            class DummyCursor:
                def fetchall(inner_self):
                    return []
            return DummyCursor()
        def commit(self):
            pass
    monkeypatch.setattr("sermon_search.routes.get_db", lambda: DummyDBEmpty())
    response = client.post("/api/update_stats")
    assert response.status_code == 404

# Test update_stats API route success
def test_update_stats_success(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.verify_api_token", lambda: (True, None))
    monkeypatch.setattr("sermon_search.routes.get_db", dummy_get_db_stats)
    response = client.post("/api/update_stats")
    assert response.status_code == 200
    assert b"ok" in response.data

# Test update_stats API route with database error
def test_update_stats_db_error(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.verify_api_token", lambda: (True, None))
    monkeypatch.setattr("sermon_search.routes.get_db", lambda: (_ for _ in ()).throw(Exception("DB error")))
    response = client.post("/api/update_stats")
    assert response.status_code == 500

# Tests for /api/ai_sermon_content endpoint

def test_ai_sermon_content_no_payload(client):
    response = client.post("/api/ai_sermon_content", data="Not JSON", content_type="application/json")
    assert response.status_code == 400

def test_ai_sermon_content_missing_field(client):
    payload = {
        "sermon_guid": str(uuid.uuid4()),
        # Missing 'ai_summary'
        "ai_summary_es": "Resumen",
        "bible_books": "Book",
        "bible_books_es": "Libro",
        "created_at": "2025-01-01 12:00:00",
        "key_quotes": "Quote",
        "key_quotes_es": "Cita",
        "sentiment": "Good",
        "sentiment_es": "Bueno",
        "sermon_style": "Expository",
        "sermon_style_es": "Expositivo",
        "status": "completed",
        "topics": "Test",
        "topics_es": "Prueba",
        "updated_at": "2025-01-01 12:00:00"
    }
    response = client.post("/api/ai_sermon_content", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert b"Missing field" in response.data

def test_ai_sermon_content_invalid_guid(client):
    payload = {
        "sermon_guid": "invalid",
        "ai_summary": "Test summary",
        "ai_summary_es": "Resumen",
        "bible_books": "Book",
        "bible_books_es": "Libro",
        "created_at": "2025-01-01 12:00:00",
        "key_quotes": "Quote",
        "key_quotes_es": "Cita",
        "sentiment": "Good",
        "sentiment_es": "Bueno",
        "sermon_style": "Expository",
        "sermon_style_es": "Expositivo",
        "status": "completed",
        "topics": "Test",
        "topics_es": "Prueba",
        "updated_at": "2025-01-01 12:00:00"
    }
    response = client.post("/api/ai_sermon_content", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert b"Invalid sermon_guid format" in response.data

def test_ai_sermon_content_invalid_datetime(client):
    payload = {
        "sermon_guid": str(uuid.uuid4()),
        "ai_summary": "Test summary",
        "ai_summary_es": "Resumen",
        "bible_books": "Book",
        "bible_books_es": "Libro",
        "created_at": "2025-01-01",  # invalid format
        "key_quotes": "Quote",
        "key_quotes_es": "Cita",
        "sentiment": "Good",
        "sentiment_es": "Bueno",
        "sermon_style": "Expository",
        "sermon_style_es": "Expositivo",
        "status": "completed",
        "topics": "Test",
        "topics_es": "Prueba",
        "updated_at": "2025-01-01 12:00:00"
    }
    response = client.post("/api/ai_sermon_content", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert b"Invalid datetime format for created_at" in response.data

def test_ai_sermon_content_valid(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.verify_api_token", lambda: (True, None))
    monkeypatch.setattr("sermon_search.routes.get_db", lambda: DummyDB())
    payload = {
        "sermon_guid": str(uuid.uuid4()),
        "ai_summary": "Test summary",
        "ai_summary_es": "Resumen",
        "bible_books": "Book",
        "bible_books_es": "Libro",
        "created_at": "2025-01-01 12:00:00",
        "key_quotes": "Quote",
        "key_quotes_es": "Cita",
        "sentiment": "Good",
        "sentiment_es": "Bueno",
        "sermon_style": "Expository",
        "sermon_style_es": "Expositivo",
        "status": "completed",
        "topics": "Test",
        "topics_es": "Prueba",
        "updated_at": "2025-01-01 12:00:00"
    }
    response = client.post("/api/ai_sermon_content", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 200
    data_resp = json.loads(response.data)
    assert data_resp.get("message") == "ok"

def test_ai_sermon_content_db_error(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.verify_api_token", lambda: (True, None))
    monkeypatch.setattr("sermon_search.routes.get_db", lambda: (_ for _ in ()).throw(Exception("DB error")))
    payload = {
        "sermon_guid": str(uuid.uuid4()),
        "ai_summary": "Test summary",
        "ai_summary_es": "Resumen",
        "bible_books": "Book",
        "bible_books_es": "Libro",
        "created_at": "2025-01-01 12:00:00",
        "key_quotes": "Quote",
        "key_quotes_es": "Cita",
        "sentiment": "Good",
        "sentiment_es": "Bueno",
        "sermon_style": "Expository",
        "sermon_style_es": "Expositivo",
        "status": "completed",
        "topics": "Test",
        "topics_es": "Prueba",
        "updated_at": "2025-01-01 12:00:00"
    }
    response = client.post("/api/ai_sermon_content", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 500

# Tests for upload_sermon endpoint

def test_upload_sermon_missing_fields(client):
    response = client.post("/upload_sermon", data={})
    assert response.status_code == 400

def test_upload_sermon_valid(client, monkeypatch):
    monkeypatch.setattr("sermon_search.routes.verify_api_token", lambda: (True, None))
    monkeypatch.setattr("sermon_search.routes.get_db", lambda: DummyDBUpload())
    form_data = {
        "audiofile": (io.BytesIO(b"dummy audio content"), "dummy.mp3"),
        "Transcription": "Test transcription",
        "SermonGUID": str(uuid.uuid4()),
        "SermonTitle": "Test Sermon",
        "Language": "en",
        "Categories": "Test",
        "Church": "Test Church",
        "TranscriptionTimings": "timing"
    }
    response = client.post("/upload_sermon", data=form_data, content_type="multipart/form-data")
    assert response.status_code == 200
    data_resp = json.loads(response.data)
    assert "message" in data_resp
