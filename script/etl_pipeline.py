# ==========================================
# 1. Configuration & Imports
# ==========================================
import pandas as pd
from sqlalchemy import create_engine, inspect
from datetime import datetime
import os
import pymysql
import gzip
# Imports from other scripts
from db_backup import get_db_engine, create_backup, SOURCE_DB_CONFIG, drop_all_tables
from transformation import (
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
    pick_df = pd.read_sql("SELECT * FROM pick_data", source_engine)
    product_df = pd.read_sql("SELECT * FROM product_data", source_engine)
    
    return pick_df, product_df

def transform_pipeline(pick_df, product_df):
    """Orchestrates transformation using functions from transformation.py."""
    print("--- Transforming Data ---")

    # 1. Basic Cleaning & IDs
    pick_df['date'] = pd.to_datetime(pick_df['date'])
    pick_df['pick_id'] = range(1, len(pick_df) + 1)
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
    summaries = pd.concat([
        summarize_year(cleaned_picks[cleaned_picks['year_of_order'] == y]) 
        for y in years
    ])

    # 4. Product Dimensions
    cleaned_prod_df = clean_products(product_df)
    
    dim_products = cleaned_picks[['product_id', 'warehouse_section', 'quantity_unit']].copy().drop_duplicates()
    dim_products['product_group_num'] = dim_products['product_id'].map(
        cleaned_prod_df.set_index('product_id')['product_group']
    )

    dim_product_groups = create_product_groups(product_df)

    # 5. Date Dimension
    dim_date = create_date_table(summaries)

    return {
        "final_order_summary": summaries,
        "dim_date": dim_date,
        "dim_products": dim_products,
        "dim_product_groups": dim_product_groups,
        "fact_picks_processed": cleaned_picks
    }

def load_to_source(tables_dict):
    """Loads all transformed DataFrames back into the source database."""
    print("--- Loading Data Back to Source Database ---")
    # Using the same config for the target as the source
    engine = get_db_engine(SOURCE_DB_CONFIG)
    #drop existing tables before loading new data
    drop_all_tables(engine)
    
    for table_name, df in tables_dict.items():
        df.to_sql(table_name, engine, if_exists='replace', index=False)
        print(f"Success: {table_name} updated in source DB.")

# ==========================================
# 2. Main Execution
# ==========================================

if __name__ == "__main__":
    try:
        # Step 1: Pre-ETL Backup
        print("Initializing pre-ETL backup...")
        backup_path = create_backup(SOURCE_DB_CONFIG, schema_only=False)
        print(f"Backup successfully created at: {backup_path}")

        # Step 2: Extract
        raw_picks, raw_prods = extract_from_source()

        # Step 3: Transform
        processed_data = transform_pipeline(raw_picks, raw_prods)

        # Step 4: Load back to original DB
        load_to_source(processed_data)

        print("\nETL Pipeline completed successfully.")

    except Exception as e:
        print(f"Critical error during ETL: {e}")