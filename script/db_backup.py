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

# Optional: Load & inspect schema
def load_schema(engine) -> Dict[str, List[Dict[str, Any]]]:
    """Load database schema information from engine."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    schema = {}

    for table in tables:
        schema[table] = inspector.get_columns(table)

    return schema

# Function to create a backup using mysqldump
def create_backup(
    config: Dict[str, Any],
    backup_dir: str = "backups",
    schema_only: bool = False,
    compress: bool = True
) -> str:
    """
    Create a backup of the database using mysqldump.
    Arguments:
        config: Database configuration dictionary
        backup_dir: Directory to store backups
        schema_only: If True, backup only schema without data
        compress: If True, compress backup with gzip
    Returns:
        Path to the created backup file
    Raises:
        RuntimeError: If mysqldump or gzip process fails
    """
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    extension = ".sql.gz" if compress else ".sql"
    backup_file = os.path.join(
        backup_dir,
        f"{config['database']}_{timestamp}{extension}"
    )

    # Build mysqldump command using environment variable for password (more secure)
    dump_command = [
        "mysqldump",
        "-h", config["host"],
        "-P", str(config["port"]),
        "-u", config["user"],
        config["database"]
    ]

    if schema_only:
        dump_command.insert(1, "--no-data")

    logger.info(f"Starting backup of database '{config['database']}' to {backup_file}")

    try:
        if compress:
            # Start mysqldump process
            dump_proc = subprocess.Popen(
                dump_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "MYSQL_PWD": config["password"]}
            )
            
            # Compress output into gzip
            with open(backup_file, "wb") as f:
                gzip_proc = subprocess.Popen(
                    ["gzip"],
                    stdin=dump_proc.stdout,
                    stdout=f,
                    stderr=subprocess.PIPE
                )
            
            # Close the dump stdout to allow it to receive SIGPIPE
            dump_proc.stdout.close()
            
            # Wait for gzip to complete
            gzip_stdout, gzip_stderr = gzip_proc.communicate()
            dump_stdout, dump_stderr = dump_proc.communicate()
            
            # Check for errors
            if dump_proc.returncode != 0:
                logger.error(f"mysqldump failed: {dump_stderr.decode()}")
                raise RuntimeError(f"mysqldump failed with return code {dump_proc.returncode}")
            if gzip_proc.returncode != 0:
                logger.error(f"gzip failed: {gzip_stderr.decode()}")
                raise RuntimeError(f"gzip failed with return code {gzip_proc.returncode}")
        else:
            # No compression
            with open(backup_file, "w") as f:
                result = subprocess.run(
                    dump_command,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    check=False,
                    env={**os.environ, "MYSQL_PWD": config["password"]}
                )
                if result.returncode != 0:
                    logger.error(f"mysqldump failed: {result.stderr.decode()}")
                    raise RuntimeError(f"mysqldump failed with return code {result.returncode}")

        logger.info(f"Backup completed successfully: {backup_file}")
        return backup_file
    
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        raise


if __name__ == "__main__":
    try:
        engine = get_db_engine(SOURCE_DB_CONFIG)
        schema = load_schema(engine)
        logger.info(f"Database Schema: {len(schema)} tables found")
        
        backup_path = create_backup(SOURCE_DB_CONFIG, schema_only=False, compress=True)
        logger.info(f"Backup created at: {backup_path}")
    except Exception as e:
        logger.error(f"Backup script failed: {str(e)}")
        raise

