# Import necessary libraries
import logging
import pandas as pd
import numpy as np
from flag_outlier import flag_outliers

# Configure logging
logger = logging.getLogger(__name__)

# Magic number constants
AVG_TIME_FOR_SINGLE_PICK = 30.496420  # Average time in minutes for orders with one pick
Z_SCORE_THRESHOLD = 3.0  # Threshold for outlier detection
#extracted_dfs = extract()
#extracted_product_data = extracted_dfs[1]
#extracted_pick_data = extracted_dfs[0]
# ==========================================
# 1. Transform pick_data table
# ==========================================
def transform_pick_data(pick_data: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw pick data by cleaning, creating IDs, and detecting outliers.
    Returns
    -------
    pd.DataFrame
        Transformed pick data with new columns: pick_id, year_of_order,
        and outlier_by_quantity_unit flag.
    """
    # Validate required columns
    required_cols = ['date', 'pick_volume', 'quantity_unit', 'order_number']
    missing_cols = [col for col in required_cols if col not in pick_data.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # Convert 'date' to datetime
    pick_data['date'] = pd.to_datetime(pick_data['date'])
    # Assign unique pick_id
    pick_data['pick_id'] = range(1, len(pick_data) + 1)
    # Extract year_of_order
    pick_data['year_of_order'] = pick_data['date'].dt.year.astype(str)
    # Update order_number column: 
    pick_data['order_number'] = pick_data['order_number'].astype(str) + '-' + pick_data['year_of_order']
    
    # Cleaning steps
    pick_data = pick_data.dropna().drop_duplicates()
    pick_data = pick_data[pick_data['pick_volume'] != 0]
    
    # Outlier Detection
    try:
        pick_data = flag_outliers(
            pick_data,
            value_col="pick_volume",
            group_col="quantity_unit",
            method="zscore",
            threshold=Z_SCORE_THRESHOLD,
            ddof=0
        )
        outlier_summary = pick_data.groupby('quantity_unit')['outlier_by_quantity_unit'].sum()
        logger.info(f"Outlier counts by quantity_unit:\n{outlier_summary}")
        logger.info(f"Transformed pick data shape: {pick_data.shape}")
    except Exception as e:
        logger.error(f"Error during outlier detection: {str(e)}")
        raise
    
    return pick_data

# ==========================================
# 2. Create order_summary table
# ==========================================
def create_order_summary(pick_data: pd.DataFrame) -> pd.DataFrame:
    """
    Create order summary table by aggregating pick-level data to order level.
    Parameters
    ----------
    pick_data : pd.DataFrame
        Transformed pick data with date and volume information.
    Returns
    -------
    pd.DataFrame
        Order-level summary with metrics like total volume, time to fulfill, etc.
    """
    # Validate required columns
    required_cols = ['order_number', 'origin', 'pick_volume', 'pick_id', 
                     'product_id', 'warehouse_section', 'position_in_order', 'date']
    missing_cols = [col for col in required_cols if col not in pick_data.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in pick_data: {missing_cols}")
    
    # Group by unique order ID and aggregate metrics
    order_summary = pick_data.copy().groupby('order_number').agg(
        origin = ('origin', 'first'),
        total_pick_volume = ('pick_volume', 'sum'),
        num_picks = ('pick_id', 'nunique'),
        num_products = ('product_id', 'nunique'),
        num_sections = ('warehouse_section', 'nunique'),
        num_positions = ('position_in_order', 'nunique'),
        time_of_first_pick = ('date', 'min'),
        time_of_last_pick = ('date', 'max')
    )
    # Add time_to_fulfill column
    order_summary['time_to_fulfill'] = (
        (order_summary['time_of_last_pick'] - order_summary['time_of_first_pick'])
        / np.timedelta64(1, 'm')
    )
    
    # Handle zero or missing time_to_fulfill - single chained operation (faster)
    order_summary['time_to_fulfill'] = (
        order_summary['time_to_fulfill']
        .replace(0, np.nan)
        .fillna(order_summary.groupby('num_picks')['time_to_fulfill'].transform('mean'))
        .fillna(AVG_TIME_FOR_SINGLE_PICK)
    )
    
    # Extract date from timestamp
    order_summary['date'] = order_summary['time_of_first_pick'].dt.date
    
    logger.info(f"Created order summary with {len(order_summary)} unique orders")
    return order_summary
# ==========================================
# 3. Create date_table table
# ==========================================
def create_date_table(order_summary: pd.DataFrame) -> pd.DataFrame:
    
    date_table = pd.DataFrame(order_summary['date'].unique(), columns=['date'])
    date_table['date'] = pd.to_datetime(date_table['date'])
    date_table['year'] = date_table['date'].dt.year
    date_table['month'] = date_table['date'].dt.month
    date_table['day'] = date_table['date'].dt.day
    date_table['day_of_week'] = date_table['date'].dt.dayofweek
    
    logger.info(f"Created date table with {len(date_table)} unique dates")
    return date_table
# ==========================================
# 4. Transform product_data table
# ==========================================
def transform_product_data(product_data: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw product data by cleaning and extracting product group IDs.
    Returns
    -------
    pd.DataFrame
        Transformed product data with product_group_id column.
    """

    # Validate required columns
    required_cols = ['product_group']
    missing_cols = [col for col in required_cols if col not in product_data.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Clean product_data
    product_data = product_data.dropna().drop_duplicates()
    
    # Extract product_group_id from product_group (e.g., "123_name" -> 123)
    product_data['product_group_id'] = product_data['product_group'].str.extract(r'(\d+)')
    product_data['product_group_id'] = product_data['product_group_id'].fillna(0).astype(int)
    
    # Drop original product_group column
    product_data = product_data.drop(columns=['product_group'])
    
    logger.info(f"Transformed {len(product_data)} products")
    return product_data
# ==========================================
# 5. Create product_group_data table
# ==========================================
def create_product_group_data(product_data: pd.DataFrame) -> pd.DataFrame:
    """
    Create product group dimension table by parsing product group information.
    Parameters
    ----------
    product_data : pd.DataFrame
        Raw product data containing product_group column.
    Returns
    -------
    pd.DataFrame
        Product group dimension with id and name columns.
    """
    if 'product_group' not in product_data.columns:
        raise ValueError("'product_group' column not found in product_data")

    product_group_data = (
        product_data[['product_group']]
        .drop_duplicates()
        .dropna()
        .reset_index(drop=True)
    )
    
    # Separate product_group into id and name (format: "123_product_name")
    product_group_split = product_group_data['product_group'].str.split('_', n=1, expand=True)
    product_group_data['product_group_id'] = product_group_split[0].astype(int)
    product_group_data['product_group_name'] = product_group_split[1]
    
    logger.info(f"Created product group dimension with {len(product_group_data)} groups")
    return product_group_data
# ==========================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        logger.info("Starting data transformation pipeline...")
        
        pick_data = transform_pick_data(pick_data)
        order_summary_data = create_order_summary(pick_data)
        date_table = create_date_table(order_summary_data)
        product_data = transform_product_data(product_data)
        product_group_data = create_product_group_data(product_data)
        
        logger.info("Data transformation completed successfully")
        logger.info(f"Pick data shape: {pick_data.shape}")
        logger.info(f"Order summary shape: {order_summary_data.shape}")
        logger.info(f"Date table shape: {date_table.shape}")
        logger.info(f"Product data shape: {product_data.shape}")
        logger.info(f"Product group data shape: {product_group_data.shape}")
        
    except Exception as e:
        logger.error(f"Error during data transformation: {str(e)}", exc_info=True)
        raise