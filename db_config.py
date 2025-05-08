import os
from dotenv import load_dotenv
import logging
from token_minter import tokenminter
from sqlalchemy import create_engine, event
import time
from contextlib import contextmanager
from sqlalchemy.exc import OperationalError, TimeoutError

logger = logging.getLogger(__name__)
# Load environment variables
load_dotenv(override=True)

# PostgreSQL config
postgres_username = os.getenv("DATABRICKS_CLIENT_ID")
postgres_host = os.getenv("DB_HOST")
postgres_port = os.getenv("DB_PORT")
postgres_database = os.getenv("DB_NAME")

# SQLAlchemy setup with token-aware connection pool
postgres_pool = create_engine(
    f"postgresql+psycopg://{postgres_username}:@{postgres_host}:{postgres_port}/{postgres_database}",
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,  # Recycle connections after 30 minutes
)

@event.listens_for(postgres_pool, "do_connect")
def provide_token(dialect, conn_rec, cargs, cparams):
    """Provide token for new connection."""
    try:
        logger.debug("Attempting to provide token for new connection")
        cparams["password"] = tokenminter.get_token()
    except Exception as e:
        logger.error(f"Error providing token: {str(e)}")
        raise

@contextmanager
def managed_connection():
    """Context manager for database connections with proper cleanup."""
    conn = None
    try:
        conn = postgres_pool.connect()
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



