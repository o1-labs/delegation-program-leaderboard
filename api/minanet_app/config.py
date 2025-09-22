import logging
import os


class BaseConfig(object):

    DEBUG = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes", "on")
    LOGGING_LEVEL = getattr(logging, os.environ.get("LOGGING_LEVEL", "INFO").upper())
    LOGGING_LOCATION = str(os.environ.get("LOGGING_LOCATION", "./application.log")).strip()
    
    # Database connection settings
    DB_CONNECTION_TIMEOUT = int(os.environ.get("DB_CONNECTION_TIMEOUT", "10"))
    DB_RETRY_ATTEMPTS = int(os.environ.get("DB_RETRY_ATTEMPTS", "3"))

    SNARK_HOST = str(os.environ["SNARK_HOST"]).strip()
    SNARK_PORT = int(os.environ["SNARK_PORT"])
    SNARK_USER = str(os.environ["SNARK_USER"]).strip()
    SNARK_PASSWORD = str(os.environ["SNARK_PASSWORD"]).strip()
    SNARK_DB = str(os.environ["SNARK_DB"]).strip()

    API_HOST = str(os.environ["API_HOST"]).strip()
    API_PORT = int(os.environ["API_PORT"])
    SWAGGER_HOST = str(os.environ["SWAGGER_HOST"]).strip()
    CACHE_TIMEOUT = int(os.environ["CACHE_TIMEOUT"])
