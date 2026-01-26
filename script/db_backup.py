# ==========================================
# 1. Library & Configuration
# ==========================================
import subprocess
from urllib.parse import quote_plus
from sqlalchemy import create_engine, inspect
from datetime import datetime
import os
import pymysql
import gzip


SOURCE_DB_CONFIG = {
    "user": "root",
    "password": "mysql",
    "host": "localhost",
    "port": "3306",
    "database": "obeta_db"
}
BACKUP_DIR = "./backups"

# ==========================================
# 2. Create Connection with MySQL Database
# ==========================================
def get_db_engine(config) -> create_engine:
    """Create a SQLAlchemy engine for the given database configuration."""
    password = quote_plus(config['password'])
    connection_str = (
        f"mysql+pymysql://{config['user']}:{password}"
        f"@{config['host']}:{config['port']}/{config['database']}"
    )
    return create_engine(connection_str)

# Optional: Load & inspect schema
def load_schema(engine) -> dict:
    """Load database schema using SQLAlchemy inspector."""

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    schema = {}

    for table in tables:
        schema[table] = inspector.get_columns(table)

    return schema
#Example usage: 
# source_engine = get_db_engine(SOURCE_DB_CONFIG)
# source_schema = load_schema(source_engine)

# ==========================================
# 3. Backup Database Function
# ==========================================
def create_backup(config, backup_dir="backups", schema_only=False,compress=True):
    os.makedirs(backup_dir, exist_ok=True)
    """Create a backup of the MySQL database."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extension = ".sql.gz" if compress else ".sql"
    backup_file = os.path.join(
        backup_dir,
        f"{config['database']}_{timestamp}.sql"
    )
    # Build mysqldump command
    dump_command = [
        "mysqldump",
        "-h", config["host"],
        "-P", config["port"],
        "-u", config["user"],
        f"--password={config['password']}",
        config["database"]
    ]

    if schema_only:
        dump_command.insert(1, "--no-data")

    if compress:
        # Start mysqldump process
        dump_proc = subprocess.Popen(
            dump_command,
            stdout=subprocess.PIPE
        )

        # Pipe output into gzip
        with open(backup_file, "wb") as f:
            gzip_proc = subprocess.Popen(
                ["gzip"],
                stdin=dump_proc.stdout,
                stdout=f
            )

        dump_proc.stdout.close()
        gzip_proc.communicate()

        if dump_proc.returncode not in (0, None):
            raise RuntimeError("mysqldump failed")

    else:
        # No compression
        with open(backup_file, "w") as f:
            subprocess.run(dump_command, stdout=f, check=True)

    return backup_file

# ==========================================
# 4. Drop All Tables in Schema
# ==========================================
def drop_all_tables(engine):
    """Drop all tables in the connected database."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if not tables:
        print("No tables found to drop.")
        return
    with engine.connect() as conn:
        for table in tables:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"Dropped table: {table}")

# Prevent execution on import
if __name__ == "__main__":
    engine = get_db_engine(SOURCE_DB_CONFIG)
    schema = load_schema(engine)
    print(f"Loaded schema for {len(schema)} tables")

    backup_path = create_backup(SOURCE_DB_CONFIG, schema_only=False)
    print(f"Backup created at: {backup_path}")

    drop_all_tables(engine)