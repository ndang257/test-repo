import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from typing import Optional, Literal
from urllib.parse import quote_plus

# ==========================================
# 1. Configuration
# ==========================================

# Database Configurations (Update these credentials)
SOURCE_DB_CONFIG = {
    "user": "root",
    "password": "mysql",
    "host": "localhost",
    "port": "3306",
    "database": "obeta_db"
}

TARGET_DB_CONFIG = {
    "user": "root",
    "password": "mysql",
    "host": "localhost",
    "port": "3306",
    "database": "obeta_db_staging"
}

# Helper to create connection string
def get_db_engine(config):
    # handling special characters in password
    password = quote_plus(config['password']) 
    connection_str = f"mysql+pymysql://{config['user']}:{password}@{config['host']}:{config['port']}/{config['database']}"
    return create_engine(connection_str)

# ==========================================
# 2. Transformation Helper Functions
# ==========================================

def flag_outliers_by_unit(
    df: pd.DataFrame,
    value_col: str,
    *,
    group_col: str = "quantity_unit",
    method: Literal["zscore", "modified"] = "zscore",
    threshold: Optional[float] = None,
    ddof: int = 0,
    min_group_size: int = 3,
) -> pd.DataFrame:
    """
    Logic imported from notebook to flag outliers.
    """
    if threshold is None:
        threshold = 3.0 if method == "zscore" else 3.5

    out = df.copy()
    x = pd.to_numeric(out[value_col], errors="coerce")
    flag_col = f"{value_col}_is_outlier_by_{group_col}"

    def compute_group_flags(g: pd.Series) -> pd.DataFrame:
        res = pd.DataFrame(index=g.index)
        valid = g.dropna()
        
        if valid.size < min_group_size:
            res[flag_col] = False
            return res

        if method == "zscore":
            mean = valid.mean()
            std = valid.std(ddof=ddof)
            if std == 0 or np.isnan(std):
                z = pd.Series(0.0, index=g.index)
            else:
                z = (g - mean) / std
        elif method == "modified":
            med = valid.median()
            mad = (valid - med).abs().median()
            if mad == 0 or np.isnan(mad):
                z = pd.Series(0.0, index=g.index)
            else:
                z = 0.6745 * (g - med) / mad
        else:
            raise ValueError("method must be 'zscore' or 'modified'")

        res[flag_col] = z.abs().gt(threshold).fillna(False)
        return res

    flags = x.groupby(out[group_col], dropna=False).apply(compute_group_flags)
    
    # Handle the multi-index returned by groupby.apply
    if isinstance(flags.index, pd.MultiIndex):
        flags.index = flags.index.get_level_values(-1)

    out[flag_col] = flags[flag_col]
    return out

# ==========================================
# 3. ETL Stages
# ==========================================


# ==========================================
# 4. Main Execution
# ==========================================
