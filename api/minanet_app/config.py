import logging
import os


class BaseConfig(object):

    DEBUG = False
    LOGGING_LEVEL = logging.INFO
    LOGGING_LOCATION = str(os.environ["LOGGING_LOCATION"]).strip()

    SNARK_HOST = str(os.environ["SNARK_HOST"]).strip()
    SNARK_PORT = int(os.environ["SNARK_PORT"])
    SNARK_USER = str(os.environ["SNARK_USER"]).strip()
    SNARK_PASSWORD = str(os.environ["SNARK_PASSWORD"]).strip()
    SNARK_DB = str(os.environ["SNARK_DB"]).strip()

    API_HOST = str(os.environ["API_HOST"]).strip()
    API_PORT = int(os.environ["API_PORT"])
    SWAGGER_HOST = str(os.environ["SWAGGER_HOST"]).strip()
    CACHE_TIMEOUT = int(os.environ["CACHE_TIMEOUT"])
