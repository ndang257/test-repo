# ==========================================
# 1. Configuration & Imports
# ==========================================
import pandas as pd
from sqlalchemy import create_engine, inspect,Categorical, Date, Integer, String, Float, Boolean

# Imports from other scripts
from db_backup import get_db_engine, create_backup, SOURCE_DB_CONFIG, load_schema
from script.transformation import (
    flag_outliers_by_unit,
    summarize_year,
    clean_products,
    create_product_groups,
    create_date_table
)

# ==========================================
# 2. ETL Stages
# ==========================================

def extract_from_source():
    """Extracts raw data from the source MySQL database."""
    print("--- Extracting Data from MySQL ---")
    # Uses the engine and config imported from db_backup
    source_engine = get_db_engine(SOURCE_DB_CONFIG)

    # Load raw data into DataFrames
    pick_df = pd.read_sql("SELECT * FROM pick_data LIMIT 100", source_engine)
    product_df = pd.read_sql("SELECT * FROM product_data LIMIT 100", source_engine)
    print(f"Extracted {len(pick_df)} records from pick_data")
    print(f"Extracted {len(product_df)} records from product_data")
    return pick_df, product_df
# Back up function from db_backup.py is used here
def backup_database():
    """Creates a backup of the source database."""
    print("--- Backing Up Source Database ---")
    backup_path = create_backup(SOURCE_DB_CONFIG, backup_dir="backups", schema_only=False, compress=True)
    print(f"Backup successfully created at: {backup_path}")
    return backup_path

def transform_pipeline(pick_df, product_df):
    """Orchestrates transformation using functions from transformation.py."""
    print("--- Transforming Data ---")

    # 1. Basic Cleaning & IDs
    #pick_df['date'] = pd.to_datetime(pick_df['date'])
    #pick_df['pick_id'] = range(1, len(pick_df) + 1)
    pick_df['year_of_order'] = pick_df['date'].dt.year.astype(str)
    pick_df['updated_order_number'] = (
        pick_df[['order_number', 'year_of_order']]
        .astype(str)
        .agg('-'.join, axis=1)
    )

    cleaned_picks = pick_df.dropna().drop_duplicates()
    cleaned_picks = cleaned_picks[cleaned_picks['pick_volume'] != 0]

    # 2. Outlier Detection
    cleaned_picks = flag_outliers_by_unit(cleaned_picks, value_col="pick_volume")

    # 3. Order Summaries
    years = cleaned_picks['year_of_order'].unique()
    order_summary = pd.concat([
        summarize_year(cleaned_picks[cleaned_picks['year_of_order'] == year]) 
        for year in years
    ])

    # 4. Product Dimensions
    cleaned_prod_df = clean_products(product_df)
    
    product_data = (cleaned_picks[['product_id', 'warehouse_section', 'quantity_unit']]
                    .copy()
                    .drop_duplicates()
    )

    product_data['product_group_num'] = product_data['product_id'].map(
        cleaned_prod_df.set_index('product_id')['product_group']
    )

    product_group_data = create_product_groups(product_df)

    # 5. Date Dimension
    dates = create_date_table(order_summary)

    return {
        "order_summary": order_summary,
        "dates": dates,
        "product_data": product_data,
        "product_group_data": product_group_data,
        "pick_data": cleaned_picks
    }

def load_to_source(tables_dict):
    """Loads all transformed DataFrames back into the source database."""

    print("--- Loading Data Back to Source Database ---")
    engine = get_db_engine(SOURCE_DB_CONFIG)

    #=========================
    #Data Mapping & Load
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
            "time_to_fulfil": Float()
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

    #=========================================
    # Load DataFrames into respective tables
    }
    for table_name, df in tables_dict.items():
        df.to_sql(
            table_name,
            engine,
            if_exists='replace',
            dtype=dtype_map.get(table_name),
            index=False
        )
        print(f"Success: {table_name} updated in source DB.")
    #==========================================
    #Data Definition Language (DDL) Statements (Primary & Foreign Keys)
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


# ==========================================
# 3. Main Execution
# ==========================================

if __name__ == "__main__":
    try:
        # Step 1: Pre-ETL Backup
        print("Initializing pre-ETL backup...")
        backup_path = create_backup(SOURCE_DB_CONFIG, schema_only=False, compress=True)
        print(f"Backup successfully created at: {backup_path}")

        # Step 2: Extract
        pick_df, product_df = extract_from_source()
        engine = get_db_engine(SOURCE_DB_CONFIG)
        schema = load_schema(engine)
        print(f"Loaded schema for {len(schema)} tables")

        # Step 3: Transform
        processed_data = transform_pipeline(pick_df, product_df)

        # Step 4: Load back to original DB
        load_to_source(processed_data)

        print("\nETL Pipeline completed successfully.")

    except Exception as e:
        print(f"Critical error during ETL: {e}")