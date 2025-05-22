# config/development.py
import os
from config.default import DefaultConfig

class DevelopmentConfig(DefaultConfig):
    DEBUG = True
    # Use environment variables with fallbacks to default paths
    DATABASE = os.getenv('DEV_DATABASE_PATH', './data/sermons.db')
    AUDIOFILES_DIR = os.getenv('DEV_AUDIOFILES_DIR', './data/audiofiles')
    METRICS_DATABASE = os.getenv('DEV_METRICS_DATABASE', './data/metrics.db')
    
    # Default API token for development (DO NOT USE IN PRODUCTION)
    if not os.environ.get('SERMON_API_TOKEN'):
        os.environ['SERMON_API_TOKEN'] = 'ABC123ABC123'

    # Directory creation is moved to app initialization to avoid permission issues during import
    @classmethod
    def init_directories(cls):
        """Create necessary directories if they don't exist."""
        try:
            os.makedirs(os.path.dirname(cls.DATABASE), exist_ok=True)
            os.makedirs(cls.AUDIOFILES_DIR, exist_ok=True)
        except (PermissionError, OSError) as e:
            # Log but don't fail during tests
            import logging
            logging.warning(f"Could not create directories: {e}")
            
    @classmethod
    def init_app(cls, app):
        """Initialize the application with development-specific settings."""
        super().init_app(app) if hasattr(super(), 'init_app') else None
        app.logger.info(f"Using development API token: {os.environ.get('SERMON_API_TOKEN')}")
        cls.init_directories()
