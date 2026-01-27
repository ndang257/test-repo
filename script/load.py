# ==========================================
# 1. Library & Configuration
# ==========================================

import subprocess
import pandas as pd
from urllib.parse import quote_plus
from sqlalchemy import (
    create_engine, 
    inspect, 
    Categorical, Date, Integer, String, Float, Boolean, Interval
)
from datetime import datetime
import os
import gzip
import glob

SOURCE_DB_CONFIG = {
    "user": "root",
    "password": "mysql",
    "host": "localhost",
    "port": "3306",
    "database": "obeta_db"
}
BACKUP_DIR = "./backups"

pick_data_config = {
    "file_path": r"./data_to_process/*",
    "columns": ['product_id', 
                'warehouse_section', 
                'origin', 
                'order_number', 
                'position_in_order', 
                'pick_volume', 
                'quantity_unit', 
                'date'],
    "dtypes": {
        'product_id': 'string', 
        'warehouse_section': 'category',
        'origin': 'category',
        'order_number': 'string',
        'position_in_order':'int64',
        'pick_volume': 'int64',
        'quantity_unit': 'string',
        'date': 'string'
    }
}
product_data_config = {
    "file_path": r"./product_data/products.csv",
    "columns": ['product_id', 'product_description', 'product_group'],
    "dtypes": {
        'product_id': 'string',
        'product_description': 'string',
        'product_group': 'category',
    }
}

# ==========================================
# 2. Load Database Function
# ==========================================

#read .csv files in as dataframe
def extract_from_csv(file):
    df = pd.read_csv(file['file_path'], names = file['columns'], dtype = file['dtypes'])
    return df
#read .json files in as dataframe
def extract_from_json(file):
    df = pd.read_json(file, orient = 'split')
    return df
#read .xml files in as dataframe
def extract_from_xlsx(file):
    df = pd.read_excel(file)
    return df

def extract(file_configs = [pick_data_config, product_data_config]):
    """Extract data from various file formats into pandas DataFrames."""
    df = pd.DataFrame()
    for csv_file in file_configs:
        df = df.append(extract_from_csv(csv_file), ignore_index = True)
    for xlsx_file in glob.glob("./*.xlsx"):
        df = df.append(extract_from_xlsx(xlsx_file), ignore_index = True)
        
    for json_file in glob.glob("./*.json"):
        df = df.append(extract_from_json(json_file), ignore_index = True)
    
    print(f"Extracted {len(df)} records from various file formats.")
    print(df.head())
    print(df.dtypes)
    print(df.shape)
    return df

# ==========================================
# 3. Create Connection with MySQL Database
# ==========================================
def get_engine(config) -> create_engine:
    """Create a SQLAlchemy engine for the given database configuration."""
    password = quote_plus(config['password'])
    connection_str = (
        f"mysql+pymysql://{config['user']}:{password}"
        f"@{config['host']}:{config['port']}/{config['database']}"
    )
    print(f"Connection String: {connection_str}")
    return create_engine(connection_str)

# Optional: Load & inspect schema
def load_schema(engine) -> dict:
    """Load database schema using SQLAlchemy inspector."""

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    schema = {}

    for table in tables:
        schema[table] = inspector.get_columns(table)
    print(f"Loaded schema for tables: {list(schema.keys())}")
    return schema

#==========================================
# 4. Backup Database Function
#==========================================
def create_backup(config, backup_dir="backups", schema_only=False, compress=True):
    """Create a backup of the MySQL database."""
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
    print(f"Backup successfully created at: {backup_file}")
    return backup_file

#==========================================
# 5. Load to Database Function
#==========================================
def load_to_db(table_config):
    """Load a pandas DataFrame into a MySQL database table."""
    dtype_map = {
        "order_summary": {
            "updated_order_number": String(),
            "date": Date(),
            "origin": Categorical(2),

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
            "day_of_week": String()
        },
        "product_data": {
            "product_id": Integer(),
            "product_group_num": Integer(),
            "product_description": String(50),
            "quantity_unit": String(20)
        },
        "product_group_data": {
            "product_group_num": Integer(),
            "product_group_name": String(100)
        },
        "pick_data": {
            "pick_id": Integer(),
            "product_id": Integer(),
            'warehouse_section': String(20),
            "origin": String(20),
            "position_in_order": Integer(),
            "pick_volume": Float(),
            "quantity_unit": String(20),
            "date": Date(),
            'year_of_order': String(4),
            'updated_order_number': Integer(),
            "pick_volume_is_outlier_by_quantity_unit": Boolean()
        }
    }
    
    for table_name, df in table_config.items():
        try:
            df.to_sql(
                name=table_name, 
                con=engine, 
                if_exists='replace',
                dtype=dtype_map.get(table_name) 
                index=False)
            print(f"Loaded {len(df)} records into table '{table_name}'.")
        except Exception as e:
        print(f"Error loading data into table '{table_name}': {e}")
    # Add primary and foreign key constraints
    ddl_statements = [
        #Primary keys
        "ALTER TABLE order_summary ADD PRIMARY KEY (updated_order_number);",
        "ALTER TABLE product_group_data ADD PRIMARY KEY (product_group_num);",
        "ALTER TABLE pick_data ADD PRIMARY KEY (pick_id);",
        "ALTER TABLE product_data ADD PRIMARY KEY (product_id);",
        "ALTER TABLE dates ADD PRIMARY KEY (date);",
        #Foreign keys
        "ALTER TABLE product_data ADD CONSTRAINT fk_product_group FOREIGN KEY (product_group_num) REFERENCES product_group_data(product_group_num);",
        "ALTER TABLE pick_data ADD CONSTRAINT fk_product FOREIGN KEY (product_id) REFERENCES product_data(product_id);",
        "ALTER TABLE pick_data ADD CONSTRAINT fk_order_summary FOREIGN KEY (updated_order_number) REFERENCES order_summary(updated_order_number);",
        "ALTER TABLE order_summary ADD CONSTRAINT fk_date FOREIGN KEY (date) REFERENCES dates(date);"
    ]
    with engine.connect() as conn:
        for ddl in ddl_statements:
            conn.execute(ddl)
            print(f"Executed DDL: {ddl}")


if __name__ == "__main__":
    engine = get_engine(SOURCE_DB_CONFIG)
    schema = load_schema(engine)
    data_df = extract(pick_data_config, product_data_config)
    backup_path = create_backup(SOURCE_DB_CONFIG, schema_only=False, compress=True)

    load_to_db(data_df)