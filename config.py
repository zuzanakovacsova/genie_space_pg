import os
from dotenv import load_dotenv
from pydantic import BaseSettings, Field
from typing import Optional

class DatabaseConfig(BaseSettings):
    username: str
    host: str
    port: str
    database: str
    pool_size: int = Field(default=5)
    max_overflow: int = Field(default=10)
    pool_timeout: int = Field(default=30)
    pool_recycle: int = Field(default=1800)

    class Config:
        env_prefix = "DB_"

class DatabricksConfig(BaseSettings):
    client_id: str
    client_secret: str
    host: str
    space_id: str

    class Config:
        env_prefix = "DATABRICKS_"

class Settings(BaseSettings):
    db: DatabaseConfig = DatabaseConfig()
    databricks: DatabricksConfig = DatabricksConfig()

    @property
    def database_url(self) -> str:
        return f"postgresql+psycopg2://{self.db.username}:@{self.db.host}:{self.db.port}/{self.db.database}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

# Load environment variables
load_dotenv(override=True)

# Create global config instance
config = Settings() 