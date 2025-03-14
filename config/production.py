# config/production.py
from config.default import DefaultConfig

class ProductionConfig(DefaultConfig):
    DEBUG = False
