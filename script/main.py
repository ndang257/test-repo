# ==========================================
# main.py — ETL Script
# ==========================================

import logging
import time
from datetime import datetime

# Extract
from extract import extract

# Transform
from transformation import (
    transform_pick_data,
    create_order_summary,
    create_date_table,
    transform_product_data,
    create_product_group_data
)

# Load
from load import (
    get_engine,
    create_backup,
    load_to_db,
    SOURCE_DB_CONFIG
)

# ------------------------------------------
# Logging configuration
# ------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MAIN_PIPELINE")

# ------------------------------------------
# Main Execution Function
# ------------------------------------------
def run_pipeline():
    engine = None  # Track engine for proper cleanup
    try:
        logger.info("="*60)
        logger.info(f"Starting ETL pipeline at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)
        
        start_time = time.time()

        # ======================================
        # 1. EXTRACT
        # ======================================
        extract_start = time.time()
        logger.info("[1/5] Extracting data...")
        extracted_dfs = extract()

        if len(extracted_dfs) < 2:
            raise RuntimeError(
                "Extraction failed: expected pick_data and product_data"
            )

        pick_data_raw = extracted_dfs[0]
        product_data_raw = extracted_dfs[1]
        logger.info(f"  Extraction completed in {time.time() - extract_start:.2f}s")
        logger.info(f"    - pick_data: {pick_data_raw.shape}")
        logger.info(f"    - product_data: {product_data_raw.shape}")

        # ======================================
        # 2. TRANSFORM
        # ======================================
        transform_start = time.time()
        logger.info("[2/5] Transforming data...")

        pick_data = transform_pick_data(pick_data_raw)
        order_summary = create_order_summary(pick_data)
        date_table = create_date_table(order_summary)
        product_data = transform_product_data(product_data_raw.copy())
        product_group_data = create_product_group_data(product_data_raw)

        logger.info(f"  Transformation completed in {time.time() - transform_start:.2f}s")
        logger.info(f"    - pick_data: {pick_data.shape}")
        logger.info(f"    - order_summary: {order_summary.shape}")
        logger.info(f"    - date_table: {date_table.shape}")
        logger.info(f"    - product_data: {product_data.shape}")
        logger.info(f"    - product_group_data: {product_group_data.shape}")
        
        # Clear raw data to save memory before loading
        del extracted_dfs, pick_data_raw, product_data_raw

        # Package all tables for loading
        table_config = {
            "pick_data": pick_data,
            "order_summary": order_summary,
            "dates": date_table,
            "product_data": product_data,
            "product_group_data": product_group_data,
        }

        # ======================================
        # 3. LOAD
        # ======================================
        load_start = time.time()
        logger.info("[3/5] Connecting to database...")
        engine = get_engine(SOURCE_DB_CONFIG)
        logger.info("Connected")

        logger.info("[4/5] Creating database backup...")
        backup_start = time.time()
        create_backup(SOURCE_DB_CONFIG, compress=True)
        logger.info(f"Backup completed in {time.time() - backup_start:.2f}s")

        logger.info("[5/5] Loading data into database...")
        load_to_db(engine, table_config)
        logger.info(f"Load completed in {time.time() - load_start:.2f}s")

        # Final summary
        total_time = time.time() - start_time
        logger.info("="*60)
        logger.info(f"ETL pipeline completed successfully in {total_time:.2f}s")
        logger.info("="*60)

    except Exception as e:
        logger.error("="*60)
        logger.error("ETL pipeline failed", exc_info=True)
        logger.error("="*60)
        raise
    finally:
        # Ensure database connection is properly closed
        if engine is not None:
            logger.info("Closing database connection...")
            engine.dispose()
            logger.info("Connection closed")

if __name__ == "__main__":
    run_pipeline()

