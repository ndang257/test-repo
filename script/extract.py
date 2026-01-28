# ==========================================
# 1. Library & Configuration
# ==========================================

import pandas as pd
import glob
import os
from pathlib import Path
from typing import Dict, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the script directory for relative paths
SCRIPT_DIR = Path(__file__).parent.resolve()
CSV_DIR = SCRIPT_DIR / "csv"

pick_data_config = {
    "file_path": CSV_DIR / "pick_data.csv",
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
    "file_path": CSV_DIR / "product_data.csv",
    "columns": ['product_id', 'product_description', 'product_group'],
    "dtypes": {
        'product_id': 'string',
        'product_description': 'string',
        'product_group': 'string',
    }

}

# ==========================================
# 2. Extract Functions
# ==========================================

def extract_from_csv(file_config: Dict) -> pd.DataFrame:
    """Read CSV file as dataframe with error handling.
    Args:
        file_config: Dict containing 'file_path', 'columns', and 'dtypes'
    Returns:
        pd.DataFrame: Loaded data
    """
    try:
        file_path = Path(file_config['file_path'])
        if not file_path.exists():
            logger.warning(f"CSV file not found: {file_path}")
            return pd.DataFrame()
            
        df = pd.read_csv(
            file_path, 
            names=file_config['columns'], 
            dtype=file_config['dtypes'],
            encoding='latin-1',
            header=0  # Skip first row if it's a header
        )
        logger.info(f"Successfully extracted {len(df)} records from {file_path.name}")
        return df
    except Exception as e:
        logger.error(f"Error extracting from CSV {file_config['file_path']}: {e}")
        return pd.DataFrame()


def extract_from_json(file_path: str) -> pd.DataFrame:
    """Read JSON file as dataframe with error handling.
    Args:
        file_path: Path to JSON file
    Returns:
        pd.DataFrame: Loaded data
    """
    try:
        df = pd.read_json(file_path, orient='split')
        logger.info(f"Successfully extracted {len(df)} records from {Path(file_path).name}")
        return df
    except Exception as e:
        logger.error(f"Error extracting from JSON {file_path}: {e}")
        return pd.DataFrame()
    
def extract_from_xlsx(file_path: str) -> pd.DataFrame:
    """Read Excel file as dataframe with error handling.
    Args:
        file_path: Path to Excel file
    Returns:
        pd.DataFrame: Loaded data
    """
    try:
        df = pd.read_excel(file_path)
        logger.info(f"Successfully extracted {len(df)} records from {Path(file_path).name}")
        return df
    except Exception as e:
        logger.error(f"Error extracting from XLSX {file_path}: {e}")
        return pd.DataFrame()


def extract(file_configs: List[Dict] = None) -> List[pd.DataFrame]:
    """Extract data from various file formats into separate DataFrames.
    Args:
        file_configs: List of config dicts for CSV files to extract
    Returns:
        List[pd.DataFrame]: List of DataFrames, one for each file source
    """
    if file_configs is None:
        file_configs = [pick_data_config, product_data_config]
    
    dfs = []
    
    # Extract from configured CSV files
    for csv_config in file_configs:
        df = extract_from_csv(csv_config)
        if not df.empty:
            dfs.append(df)
    
    # Extract from XLSX files in current directory
    for xlsx_file in glob.glob(str(SCRIPT_DIR / "*.xlsx")):
        df = extract_from_xlsx(xlsx_file)
        if not df.empty:
            dfs.append(df)
    
    # Extract from JSON files in current directory
    for json_file in glob.glob(str(SCRIPT_DIR / "*.json")):
        df = extract_from_json(json_file)
        if not df.empty:
            dfs.append(df)
    
    # Return list of dataframes
    if dfs:
        logger.info(f"Extracted {len(dfs)} DataFrames from various file formats.")
        total_records = sum(len(df) for df in dfs)
        logger.info(f"Total records across all sources: {total_records}")
        return dfs
    else:
        logger.warning("No data extracted from any sources.")
        return []

# ==========================================
# 3. Execution
# ==========================================
if __name__ == "__main__":
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
        #save to separate variables for further processing
        extracted_pick_data = data_dfs[0] if len(data_dfs) > 0 else None
        extracted_product_data = data_dfs[1] if len(data_dfs) > 1 else None
        
        logger.info(f"Extracted pick_data records: {len(extracted_pick_data) if extracted_pick_data is not None else 0}")
        logger.info(f"Extracted product_data records: {len(extracted_product_data) if extracted_product_data is not None else 0}")
        logger.info("Extraction complete.")
        

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise
