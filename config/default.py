# config/default.py
import logging

class DefaultConfig:
    DEBUG = True

    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_SUPPORTED_LOCALES = ['en', 'es']
    BABEL_TRANSLATION_DIRECTORIES = 'translations'

    # Configure logging
    logging.basicConfig(level=logging.DEBUG)
