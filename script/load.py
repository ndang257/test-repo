# ==========================================
# 1. Library & Configuration
# ==========================================
import subprocess
from urllib.parse import quote_plus
from sqlalchemy import (
    create_engine, 
    inspect, 
    Date, Integer, String, Float, Boolean, Interval, Text,
    text
)
from datetime import datetime
import os
import gzip
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SOURCE_DB_CONFIG = {
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "mysql"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "3306"),
    "database": os.getenv("DB_NAME", "obeta_db")
}
BACKUP_DIR = "./backups"

# ==========================================
# 2. Create Connection with MySQL Database
# ==========================================
def get_engine(config) -> create_engine:
    """Create a SQLAlchemy engine for the given database configuration."""
    password = quote_plus(config['password'])
    connection_str = (
        f"mysql+pymysql://{config['user']}:{password}"
        f"@{config['host']}:{config['port']}/{config['database']}"
    )
    logger.info(f"Connecting to database: {config['host']}:{config['port']}/{config['database']}")
    return create_engine(connection_str)

# Optional: Load & inspect schema
def load_schema(engine) -> dict:
    """Load database schema using SQLAlchemy inspector."""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        schema = {}

        for table in tables:
            schema[table] = inspector.get_columns(table)
        logger.info(f"Loaded schema for tables: {list(schema.keys())}")
        return schema
    except Exception as e:
        logger.error(f"Error loading schema: {e}")
        raise

#==========================================
# 3. Backup Database Function
#==========================================
def create_backup(config, backup_dir="backups", schema_only=False, compress=True):
    """Create a backup of the MySQL database."""
    try:
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = ".sql.gz" if compress else ".sql"

        backup_file = os.path.join(
            backup_dir,
            f"{config['database']}_{timestamp}{extension}"
        )

        # Build mysqldump command
        dump_command = [
            "mysqldump",
            "-h", config["host"],
            "-P", str(config["port"]),
            "-u", config["user"],
            f"--password={config['password']}",
            config["database"]
        ]

        if schema_only:
            dump_command.insert(1, "--no-data")

        if compress:
            # Stream mysqldump output directly into gzip
            with gzip.open(backup_file, "wb") as gz:
                result = subprocess.run(
                    dump_command,
                    stdout=gz,
                    stderr=subprocess.PIPE,
                    check=False,
                )

            if result.returncode != 0:
                raise RuntimeError(
                    f"mysqldump failed:\n{result.stderr.decode(errors='ignore')}"
                )

        else:
            # No compression
            with open(backup_file, "w") as file:
                result = subprocess.run(
                    dump_command,
                    stdout=file,
                    stderr=subprocess.PIPE,
                    check=False,
                )

            if result.returncode != 0:
                raise RuntimeError(
                    f"mysqldump failed:\n{result.stderr.decode(errors='ignore')}"
                )
        logger.info(f"Backup successfully created at: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        raise

#==========================================
# 4. Load to Database Function
#==========================================
def load_to_db(engine, table_config):
    """Load a pandas DataFrame into a MySQL database table."""
    dtype_map = {
        "order_summary": {
            "order_number": String(50),
            "date": Date(),
            "origin": String(50),

            "total_pick_volume": Integer(),
            "num_picks": Integer(),
            "num_products": Integer(),
            "num_sections": Integer(),
            "num_positions": Integer(),
            "time_to_fulfil": Interval()
        },
        "dates": {
            "date": Date(),
            "year": Integer(),
            "month": Integer(),
            "day": Integer(),
            "day_of_week": String(20)
        },
        "product_data": {
            "product_id": String(50),
            "product_group_id": String(50),
            "product_description": Text(),
            "quantity_unit": String(20)
        },
        "product_group_data": {
            "product_group_id": String(50),
            "product_group_name": String(255)
        },
        "pick_data": {
            "pick_id": Integer(),
            "product_id": String(50),
            'warehouse_section': String(50),
            "origin": String(50),
            "position_in_order": Integer(),
            "pick_volume": Float(),
            "quantity_unit": String(20),
            "date": Date(),
            'year_of_order': String(4),
            'order_number': String(50),
            "outlier_by_quantity_unit": Boolean()
        }
    }
    
    for table_name, df in table_config.items():
        try:
            df.to_sql(
                name=table_name, 
                con=engine, 
                if_exists='replace',
                dtype=dtype_map.get(table_name), 
                index=False,
                chunksize=5000  
            )
            logger.info(f"Loaded {len(df)} records into table '{table_name}'.")
        except Exception as e:
            logger.error(f"Error loading data into table '{table_name}': {e}")
            raise
    # Add primary and foreign key constraints
    ddl_statements = [
        # Primary keys
        "ALTER TABLE order_summary ADD PRIMARY KEY (order_number);",
        "ALTER TABLE product_group_data ADD PRIMARY KEY (product_group_id);",
        "ALTER TABLE pick_data ADD PRIMARY KEY (pick_id);",
        "ALTER TABLE product_data ADD PRIMARY KEY (product_id);",
        "ALTER TABLE dates ADD PRIMARY KEY (date);",
        # Foreign keys
        "ALTER TABLE product_data ADD CONSTRAINT fk_product_group FOREIGN KEY (product_group_id) REFERENCES product_group_data(product_group_id);",
        "ALTER TABLE pick_data ADD CONSTRAINT fk_product FOREIGN KEY (product_id) REFERENCES product_data(product_id);",
        "ALTER TABLE pick_data ADD CONSTRAINT fk_order_summary FOREIGN KEY (order_number) REFERENCES order_summary(order_number);",
        "ALTER TABLE order_summary ADD CONSTRAINT fk_date FOREIGN KEY (date) REFERENCES dates(date);"
    ]
    
    # Add indexes for query performance
    index_statements = [
        "CREATE INDEX idx_pick_date ON pick_data(date);",
        "CREATE INDEX idx_order_date ON order_summary(date);",
        "CREATE INDEX idx_pick_product ON pick_data(product_id);",
        "CREATE INDEX idx_product_group ON product_data(product_group_id);"
    ]
    
    # Execute with transaction management
    with engine.begin() as conn:
        # Execute DDL statements
        for ddl in ddl_statements:
            try:
                conn.execute(text(ddl))
                logger.info(f"Executed DDL: {ddl}")
            except Exception as e:
                logger.warning(f"DDL statement failed (may already exist): {ddl}. Error: {e}")
        
        # Execute index creation statements
        for idx_stmt in index_statements:
            try:
                conn.execute(text(idx_stmt))
                logger.info(f"Created index: {idx_stmt}")
            except Exception as e:
                logger.warning(f"Index creation failed (may already exist): {idx_stmt}. Error: {e}")


if __name__ == "__main__":
    try:
        engine = get_engine(SOURCE_DB_CONFIG)
        schema = load_schema(engine)
        backup_path = create_backup(SOURCE_DB_CONFIG, schema_only=False, compress=True)
        
        # Create a dictionary with sample data - replace with actual data
        table_data = {}
        
        if table_data:
            load_to_db(engine, table_data)
            logger.info("Database load completed successfully.")
        else:
            logger.warning("No data to load. Please populate table_data with DataFrames.")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise