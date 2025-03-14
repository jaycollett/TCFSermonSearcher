import os
from .default import DefaultConfig

def get_config(env=None):
    if env is None:
        env = os.getenv('FLASK_ENV', 'development')

    class Config(DefaultConfig):
        pass

    if env == 'production':
        from .production import ProductionConfig
        Config.__bases__ = (ProductionConfig, DefaultConfig)
    elif env == 'development':
        from .development import DevelopmentConfig
        Config.__bases__ = (DevelopmentConfig, DefaultConfig)

    return Config