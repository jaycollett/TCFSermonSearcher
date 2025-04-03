# config/production.py
import os
from config.default import DefaultConfig

class ProductionConfig(DefaultConfig):
    DEBUG = False
    # Use environment variables with fallbacks to default paths
    DATABASE = os.getenv('PROD_DATABASE_PATH', '/data/sermons.db')
    AUDIOFILES_DIR = os.getenv('PROD_AUDIOFILES_DIR', '/data/audiofiles')
    METRICS_DATABASE = os.getenv('PROD_METRICS_DATABASE', '/data/metrics.db')
    SHARED_IMAGES_DIR = os.getenv('PROD_SHARED_IMAGES_DIR', '/data/shared_images')

    # Directory creation is moved to app initialization to avoid permission issues during import
    @classmethod
    def init_directories(cls):
        """Create necessary directories if they don't exist."""
        try:
            os.makedirs(os.path.dirname(cls.DATABASE), exist_ok=True)
            os.makedirs(cls.AUDIOFILES_DIR, exist_ok=True)
            os.makedirs(cls.SHARED_IMAGES_DIR, exist_ok=True)
        except (PermissionError, OSError) as e:
            # Log but don't fail during tests
            import logging
            logging.warning(f"Could not create directories: {e}")