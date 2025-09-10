import time
import psycopg2
from psycopg2 import OperationalError
from config import BaseConfig
from logger_util import logger


class DatabaseHealthChecker:
    """Database health monitoring and connection management"""
    
    def __init__(self):
        self.connection_params = {
            'host': BaseConfig.SNARK_HOST,
            'port': BaseConfig.SNARK_PORT,
            'database': BaseConfig.SNARK_DB,
            'user': BaseConfig.SNARK_USER,
            'password': BaseConfig.SNARK_PASSWORD,
            'connect_timeout': BaseConfig.DB_CONNECTION_TIMEOUT,
        }
        
    def get_connection_with_retry(self):
        """Get database connection with retry logic and detailed logging"""
        last_exception = None
        
        for attempt in range(1, BaseConfig.DB_RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"Database connection attempt {attempt}/{BaseConfig.DB_RETRY_ATTEMPTS}")
                logger.debug(f"Connecting to {BaseConfig.SNARK_HOST}:{BaseConfig.SNARK_PORT}/{BaseConfig.SNARK_DB} as {BaseConfig.SNARK_USER}")
                
                connection = psycopg2.connect(**self.connection_params)
                logger.info("Database connection established successfully")
                return connection
                
            except OperationalError as e:
                last_exception = e
                logger.warning(f"Database connection attempt {attempt} failed: {e}")
                
                if attempt < BaseConfig.DB_RETRY_ATTEMPTS:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    
        logger.error(f"All database connection attempts failed. Last error: {last_exception}")
        raise ValueError(f"Database connection failed after {BaseConfig.DB_RETRY_ATTEMPTS} attempts: {last_exception}")
    
    def check_database_health(self):
        """Comprehensive database health check"""
        health_status = {
            'status': 'unknown',
            'connection': False,
            'query_test': False,
            'response_time_ms': None,
            'error': None
        }
        
        start_time = time.time()
        
        try:
            # Test connection
            connection = self.get_connection_with_retry()
            health_status['connection'] = True
            logger.debug("Database connection health check passed")
            
            # Test basic query
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 as health_check")
                result = cursor.fetchone()
                
                if result and result[0] == 1:
                    health_status['query_test'] = True
                    logger.debug("Database query health check passed")
                else:
                    logger.warning("Database query health check returned unexpected result")
                    
            connection.close()
            health_status['status'] = 'healthy'
            
        except Exception as e:
            health_status['error'] = str(e)
            health_status['status'] = 'unhealthy'
            logger.error(f"Database health check failed: {e}")
            
        finally:
            health_status['response_time_ms'] = round((time.time() - start_time) * 1000, 2)
            
        return health_status
    
    def get_connection_info(self):
        """Get sanitized connection information for debugging"""
        return {
            'host': BaseConfig.SNARK_HOST,
            'port': BaseConfig.SNARK_PORT,
            'database': BaseConfig.SNARK_DB,
            'user': BaseConfig.SNARK_USER,
            'timeout': BaseConfig.DB_CONNECTION_TIMEOUT,
            'retry_attempts': BaseConfig.DB_RETRY_ATTEMPTS,
        }


# Global instance
db_health_checker = DatabaseHealthChecker()