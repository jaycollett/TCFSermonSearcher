# config/development.py
from config.default import DefaultConfig

class DevelopmentConfig(DefaultConfig):
    DEBUG = True
