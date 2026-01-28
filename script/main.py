# ==========================================
# 1. Import
# ==========================================
import logging
from extract import pick_data_config, product_data_config, extract

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# 2. Extract
# ==========================================
try:
    data_dfs = extract()
    
    # Print data info for each dataframe
    if data_dfs:
        for idx, df in enumerate(data_dfs, 1):
            logger.info(f"\n--- DataFrame {idx} ---")
            logger.info(f"Shape: {df.shape}")
            logger.info(f"Columns: {list(df.columns)}")
            logger.info(f"Data types:\n{df.dtypes}")
            logger.info(f"First few records:")
            logger.info(df.head())
            logger.info(f"Memory usage: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
    else:
        logger.warning("No data to display.")
    # Save to separate variables for further processing
    extracted_pick_data = data_dfs[0] if len(data_dfs) > 0 else None
    extracted_product_data = data_dfs[1] if len(data_dfs) > 1 else None
    logger.info(f"Extracted pick_data records: {len(extracted_pick_data) if extracted_pick_data is not None else 0}")
    logger.info(f"Extracted product_data records: {len(extracted_product_data) if extracted_product_data is not None else 0}")
    logger.info("Extraction complete.")
except Exception as e:
    logger.error(f"Unexpected error: {e}")

# 3. Transformation
# ==========================================

# ==========================================
# 4. Load
# ==========================================