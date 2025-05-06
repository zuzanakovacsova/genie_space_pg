import os
from dotenv import load_dotenv
from psycopg2 import connect
import logging
import threading
from psycopg2 import pool
from token_minter import tokenminter

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

class TokenAwareConnectionPool:
    def __init__(self, minconn=1, maxconn=10):
        self.minconn = minconn
        self.maxconn = maxconn
        self._lock = threading.Lock()
        self._pool = None
        self._token = None

    def _refresh_pool(self):
        token = tokenminter.get_token()
        if self._pool is not None:
            self._pool.closeall()
        self._pool = pool.ThreadedConnectionPool(
            self.minconn, self.maxconn,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=CLIENT_ID,
            password=token,
            sslmode='require'
        )
        self._token = token
        logger.info("Refreshed connection pool with new token.")

    def getconn(self):
        with self._lock:
            current_token = tokenminter.get_token()
            if self._pool is None or self._token != current_token:
                self._refresh_pool()
            return self._pool.getconn()

    def putconn(self, conn):
        with self._lock:
            if self._pool:
                self._pool.putconn(conn)

    def closeall(self):
        with self._lock:
            if self._pool:
                self._pool.closeall()
                self._pool = None
                self._token = None

# Create a global pool instance
global_pool = TokenAwareConnectionPool()

def get_connection():
    return global_pool.getconn()

def release_connection(conn):
    global_pool.putconn(conn)

def close_pool():
    global_pool.closeall()

def close_connection(conn):
    """Close the database connection"""
    if conn is not None:
        try:
            conn.close()
            logger.info("Closed database connection")
        except Exception as e:
            logger.error(f"Error closing database connection: {str(e)}")
            raise 