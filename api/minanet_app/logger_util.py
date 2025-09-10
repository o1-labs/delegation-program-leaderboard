import logging
import sys
from config import BaseConfig
from logging.handlers import RotatingFileHandler

# Enhanced logging configuration with console output for debugging
def setup_logger():
    """Setup enhanced logger with both file and console handlers"""
    logger = logging.getLogger('leaderboard')
    logger.setLevel(BaseConfig.LOGGING_LEVEL)
    
    # Prevent duplicate logs if logger already configured
    if logger.handlers:
        return logger
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    
    # File handler with rotation (with error handling for containerized environments)
    if BaseConfig.LOGGING_LOCATION:
        try:
            import os
            log_path = BaseConfig.LOGGING_LOCATION
            
            # If it ends with .log, treat as file path directly
            if log_path.endswith('.log'):
                log_file = log_path
            else:
                # Otherwise treat as directory and append filename
                log_file = log_path.rstrip('/') + "/leaderboard.log"
            
            # Create directory if it doesn't exist
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
                
            file_handler = RotatingFileHandler(
                filename=log_file, 
                maxBytes=52428800,  # 50MB
                backupCount=10
            )
            file_handler.setFormatter(detailed_formatter)
            file_handler.setLevel(BaseConfig.LOGGING_LEVEL)
            logger.addHandler(file_handler)
            
        except Exception as e:
            # If file logging fails, continue with console only
            print(f"Warning: Could not setup file logging to {BaseConfig.LOGGING_LOCATION}: {e}")
            print("Continuing with console logging only...")
    
    # Console handler for Kubernetes logs
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(detailed_formatter)
    console_handler.setLevel(BaseConfig.LOGGING_LEVEL)
    logger.addHandler(console_handler)
    
    # Reduce noise from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    
    # Add debug info about logging setup
    if BaseConfig.DEBUG:
        logger.debug(f"Logger initialized - Level: {BaseConfig.LOGGING_LEVEL}")
        logger.debug(f"Log file: {BaseConfig.LOGGING_LOCATION if BaseConfig.LOGGING_LOCATION else 'console only'}")
    
    return logger

# Initialize the logger
logger = setup_logger()
