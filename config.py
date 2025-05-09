import os
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional

@dataclass
class DatabaseConfig:
    username: str
    host: str
    port: str
    database: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800

@dataclass
class DatabricksConfig:
    client_id: str
    client_secret: str
    host: str
    space_id: str

class Config:
    def __init__(self):
        load_dotenv(override=True)
        self.db = DatabaseConfig(
            username=os.getenv("DATABRICKS_CLIENT_ID"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            database=os.getenv("DB_NAME")
        )
        self.databricks = DatabricksConfig(
            client_id=os.getenv("DATABRICKS_CLIENT_ID"),
            client_secret=os.getenv("DATABRICKS_CLIENT_SECRET"),
            host=os.getenv("DATABRICKS_HOST"),
            space_id=os.getenv("SPACE_ID")
        )

    @property
    def database_url(self) -> str:
        return f"postgresql+psycopg2://{self.db.username}:@{self.db.host}:{self.db.port}/{self.db.database}"

config = Config() 