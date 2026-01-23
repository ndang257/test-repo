import subprocess
from urllib.parse import quote_plus
from sqlalchemy import create_engine, inspect
from datetime import datetime
import os
import pymysql
import gzip
import logging
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database Configuration - Load from environment variables for security
SOURCE_DB_CONFIG: Dict[str, Any] = {
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "mysql"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "database": os.getenv("DB_NAME", "obeta_db")
}
# Helper to create SQLAlchemy engine
def get_db_engine(config: Dict[str, Any]):
    """Create a SQLAlchemy engine for database connection."""
    password = quote_plus(config['password'])
    connection_str = (
        f"mysql+pymysql://{config['user']}:{password}"
        f"@{config['host']}:{config['port']}/{config['database']}"
    )
    return create_engine(connection_str)

