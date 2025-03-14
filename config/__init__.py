import os
from .default import DefaultConfig

def get_config(env=None):
    """
    Get configuration based on environment.
    
    Args:
        env: Environment name ('development', 'testing', 'production')
             If None, uses FLASK_ENV environment variable
    
    Returns:
        Config class with appropriate settings
    """
    if env is None:
        env = os.getenv('FLASK_ENV', 'development')

    class Config(DefaultConfig):
        pass

    # Load environment-specific config
    if env == 'production':
        from .production import ProductionConfig
        Config.__bases__ = (ProductionConfig, DefaultConfig)
    elif env == 'development':
        from .development import DevelopmentConfig
        Config.__bases__ = (DevelopmentConfig, DefaultConfig)
    elif env == 'testing':
        from .testing import TestingConfig
        Config.__bases__ = (TestingConfig, DefaultConfig)
    
    # Override with environment variables if provided
    class EnvConfig(Config):
        pass
    
    # Allow database path to be set via environment variable
    if os.getenv('DATABASE_PATH'):
        EnvConfig.DATABASE = os.getenv('DATABASE_PATH')
    
    # Allow audio files directory to be set via environment variable
    if os.getenv('AUDIOFILES_DIR'):
        EnvConfig.AUDIOFILES_DIR = os.getenv('AUDIOFILES_DIR')
    
    # Allow debug setting to be overridden
    if os.getenv('FLASK_DEBUG'):
        EnvConfig.DEBUG = os.getenv('FLASK_DEBUG').lower() in ('true', '1', 't')
    
    return EnvConfig