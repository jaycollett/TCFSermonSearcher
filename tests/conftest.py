import pytest
import os
import tempfile
from sermon_search.app_factory import create_app

def pytest_addoption(parser):
    """Add command-line options to pytest."""
    parser.addoption(
        "--config", 
        action="store", 
        default="testing", 
        help="Configuration to use: testing, development, or production"
    )

@pytest.fixture
def app(request):
    """Create and configure a Flask app for testing."""
    # Get config from environment variable with option override
    config_name = request.config.getoption("--config") or os.environ.get('FLASK_ENV', 'testing')
    
    # Create a temporary file to isolate the database for tests
    db_fd, db_path = tempfile.mkstemp()
    # Create a temp directory for audiofiles
    audio_temp_dir = tempfile.mkdtemp()
    
    # Create app with the specified config
    app = create_app(config_name)
    
    # Override with test-specific settings
    app.config.update(
        TESTING=True,
        DEBUG=True,
        DATABASE=db_path,
        AUDIOFILES_DIR=audio_temp_dir,
        SECRET_KEY='test',
        TESTING_LOGGER_LEVEL='ERROR'
    )
    
    # Create the database and load test data
    with app.app_context():
        pass  # Database is initialized in create_app
    
    yield app
    
    # Close and remove the temporary database
    os.close(db_fd)
    os.unlink(db_path)
    # Clean up the audio temp directory
    os.rmdir(audio_temp_dir)

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()