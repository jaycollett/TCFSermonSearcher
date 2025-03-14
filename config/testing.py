import os
from config.default import DefaultConfig

class TestingConfig(DefaultConfig):
    TESTING = True
    DEBUG = True
    # Use environment variables with fallbacks to default paths
    DATABASE = os.getenv('TEST_DATABASE_PATH', './data/sermons.db')
    AUDIOFILES_DIR = os.getenv('TEST_AUDIOFILES_DIR', './data/audiofiles')
    # Testing-specific settings
    SECRET_KEY = 'test-key'
    TESTING_LOGGER_LEVEL = 'ERROR'
