import logging
from sqlalchemy import create_engine, event
from contextlib import contextmanager
from sqlalchemy.exc import OperationalError, TimeoutError
from token_minter import tokenminter
from config import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.engine = create_engine(
            config.database_url,
            pool_size=config.db.pool_size,
            max_overflow=config.db.max_overflow,
            pool_timeout=config.db.pool_timeout,
            pool_recycle=config.db.pool_recycle
        )
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        @event.listens_for(self.engine, "do_connect")
        def provide_token(dialect, conn_rec, cargs, cparams):
            """Provide token for new connection."""
            try:
                logger.debug("Attempting to provide token for new connection")
                cparams["password"] = tokenminter.get_token()
            except Exception as e:
                logger.error(f"Error providing token: {str(e)}")
                raise

    @contextmanager
    def managed_connection(self):
        """Context manager for database connections with proper cleanup."""
        conn = None
        try:
            conn = self.engine.connect()
            yield conn
        except Exception as e:
            logger.error(f"Error in managed connection: {str(e)}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"Error closing connection: {str(e)}")

    def cleanup(self):
        """Clean up all resources before shutdown."""
        try:
            logger.info("Starting database cleanup")
            self.engine.dispose()
            logger.info("Database cleanup completed")
        except Exception as e:
            logger.error(f"Error during database cleanup: {str(e)}")
            raise

# Initialize database manager
db_manager = DatabaseManager()



