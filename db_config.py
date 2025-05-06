import os
from dotenv import load_dotenv
from psycopg2 import connect
import logging
import threading
from psycopg2 import pool
from token_minter import tokenminter
from databricks import sdk
from databricks.sdk.core import Config
from sqlalchemy import create_engine, event, text
import time

load_dotenv(override=True)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
CLIENT_ID = os.getenv("DATABRICKS_CLIENT_ID")

logger = logging.getLogger(__name__)
# Load environment variables
load_dotenv(override=True)

# Databricks config
app_config = Config()
workspace_client = sdk.WorkspaceClient()

# PostgreSQL config
postgres_username = app_config.client_id
postgres_host = os.getenv('DB_HOST')
postgres_port = int(os.getenv('DB_PORT', '5432'))
postgres_database = os.getenv('DB_NAME')

# SQLAlchemy setup with token-aware connection pool
postgres_pool = create_engine(
    f"postgresql+psycopg://{postgres_username}:@{postgres_host}:{postgres_port}/{postgres_database}",
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800  # Recycle connections after 30 minutes
)

postgres_password = None
last_password_refresh = time.time()

@event.listens_for(postgres_pool, "do_connect")
def provide_token(dialect, conn_rec, cargs, cparams):
    """Refresh OAuth token every 15 minutes for PostgreSQL authentication."""
    global postgres_password, last_password_refresh
    if postgres_password is None or time.time() - last_password_refresh > 900:
        print("Refreshing PostgreSQL OAuth token")
        postgres_password = workspace_client.config.oauth_token().access_token
        last_password_refresh = time.time()

    cparams["password"] = postgres_password

def get_connection():
    """Get a connection from the pool."""
    return postgres_pool.connect()

def release_connection(conn):
    """Release a connection back to the pool."""
    conn.close()

