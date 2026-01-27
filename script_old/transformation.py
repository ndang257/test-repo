#!/usr/bin/env python

# This notebook outlines the data transformation process used on two datasets provided by Obeta, `pick_data`  and `product_data` .
# 1. **Pick Data**: Transactional data regarding warehouse picks.
# 2. **Product Data**: Descriptive data regarding product hierarchies.

# ## 1. Setup and Imports
import pandas as pd
import numpy as np
from scipy import stats
from typing import Optional, Literal
from collections import Counter
from itertools import combinations
from script.db_backup import get_db_engine, SOURCE_DB_CONFIG

## 2. Initialize Database Connection & Load Data
engine = get_db_engine(SOURCE_DB_CONFIG)

# Load data from MySQL database
original_pick_data_df = pd.read_sql("SELECT * FROM pick_data", engine)
product_groups_df = pd.read_sql("SELECT * FROM product_data", engine)


## 3. Pick Data Transformation
### 3.1 pick_data table basic transformation
original_pick_data_df['date'] = pd.to_datetime(original_pick_data_df['date'])
original_pick_data_df['pick_id'] = range(1, len(original_pick_data_df) + 1)
original_pick_data_df['year_of_order'] = original_pick_data_df['date'].dt.year.astype(str)
original_pick_data_df['updated_order_number'] = (
    original_pick_data_df[['order_number', 'year_of_order']]
    .astype(str)
    .agg('-'.join, axis=1)
)

# Cleaning steps
cleaned_pick_data = original_pick_data_df.copy().dropna().drop_duplicates()
cleaned_pick_data = cleaned_pick_data[cleaned_pick_data['pick_volume'] != 0]

# cleaned_pick_data.to_parquet('cleaned_pick_data.parquet')

### 3.3 Outlier Detection
# Define a helper function to identify statistical outliers in pick volume, grouped by the unit of measure (`quantity_unit`).

def flag_outliers_by_unit(
    df: pd.DataFrame,
    value_col: str,
    *,
    group_col: str = "quantity_unit",
    method: Literal["zscore", "modified"] = "zscore",
    threshold: Optional[float] = None,
    ddof: int = 0,
    min_group_size: int = 3,
    separate_sides: bool = False,
    flag_col: Optional[str] = None,
) -> pd.DataFrame:
    """
    Flag outliers in `value_col` *per group* defined by `group_col` (e.g., quantity_unit).
    df : pd.DataFrame
        Input DataFrame.
    value_col : str
        Numeric column to analyze for outliers.
    group_col : str
        Grouping column (default: 'quantity_unit').
    method : {'zscore', 'modified'}
        'zscore' = mean/std; 'modified' = median/MAD (robust).
    threshold : float, optional
        Threshold for the chosen method. Defaults: 3.0 for zscore, 3.5 for modified.
    ddof : int
        ddof for std in zscore method.
    min_group_size : int
        Minimum group size to compute outliers. Smaller groups are marked as non-outliers.
    separate_sides : bool
        If True, adds two columns: lower/upper outliers (instead of a single boolean).
    flag_col : str, optional
        Name of the output flag column when separate_sides=False.
        Defaults to f'{value_col}_is_outlier_by_{group_col}'.
    Returns a copy of df with added outlier flag column(s).
    """

    if threshold is None:
        threshold = 3.0 if method == "zscore" else 3.5
    if flag_col is None and not separate_sides:
        flag_col = f"{value_col}_is_outlier_by_{group_col}"

    out = df.copy()
    x = pd.to_numeric(out[value_col], errors="coerce")

    def compute_group_flags(g: pd.Series) -> pd.DataFrame:
        res = pd.DataFrame(index=g.index)
        valid = g.dropna()

        # Respect minimum group size
        if valid.size < min_group_size:
            if separate_sides:
                res["is_lower_outlier"] = False
                res["is_upper_outlier"] = False
            else:
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

        if separate_sides:
            res["is_lower_outlier"] = z.lt(-threshold).fillna(False)
            res["is_upper_outlier"] = z.gt(threshold).fillna(False)
        else:
            res[flag_col] = z.abs().gt(threshold).fillna(False)

        return res

    flags = x.groupby(out[group_col], dropna=False).apply(compute_group_flags)
    flags.index = flags.index.get_level_values(-1)

    for col in flags.columns:
        out[col] = flags[col]

    return out

## 4. Order Summaries
### 4.1 Generate Summaries
#Create a function to summarize data at the order level. This calculates complexity metrics (number of picks, sections, products) and fulfillment time.

def summarize_year(df):
    # Group by unique order ID and aggregate metrics
    order_summary_data = df.groupby('updated_order_number').agg(
        origin = ('origin', 'first'),
        total_pick_volume = ('pick_volume', 'sum'),
        num_picks = ('pick_id', 'nunique'),
        num_products = ('product_id', 'nunique'),
        num_sections = ('warehouse_section', 'nunique'),
        num_positions = ('position_in_order', 'nunique'),
        time_of_first_pick = ('date', 'min'),
        time_of_last_pick = ('date', 'max')
    )
    #adding time to fulfil column
    order_summary_data['time_to_fulfil'] = (
    order_summary_data['time_of_last_pick'] - order_summary_data['time_of_first_pick']
    ) / np.timedelta64(1, 'm')
    group_means = order_summary_data.groupby('num_picks')['time_to_fulfil'].transform('mean')
    order_summary_data['time_to_fulfil'] = order_summary_data['time_to_fulfil'].replace(0, np.nan)
    order_summary_data['time_to_fulfil'] = order_summary_data['time_to_fulfil'].fillna(group_means)
    # Assign orders with one pick half the average time of orders with two picks
    order_summary_data['time_to_fulfil'] = order_summary_data['time_to_fulfil'].fillna(30.496420)

    order_summary_data['date'] = order_summary_data['time_of_first_pick'].dt.date

    return order_summary_data

# ### 4.2 Finalize order_data table
# Process orders year-by-year for efficiency and concatenate.

years = cleaned_pick_data['year_of_order'].unique()
order_summaries_by_year = []

for year in years:
    df_subset = cleaned_pick_data[cleaned_pick_data['year_of_order'] == year]
    summarized_year = summarize_year(df_subset)
    order_summaries_by_year.append(summarized_year)

final_order_data = pd.concat(order_summaries_by_year)

## 5. Product Data Transformation
### 5.1 Clean Product Data
def clean_products(df):
    df = df.dropna()
    df = df.drop_duplicates()
    # Extract only the group number prefix (e.g., '35' from '35_Leuchten')
    df['product_group'] = df['product_group'].apply(lambda x: x.split('_')[0])
    return df

cleaned_product_df = clean_products(product_groups_df)


### 5.2 Create Product Dimension Tables
# Create two tables:
# 1.  **Product Data:** Links Product ID to Warehouse Section and Group Number.
# 2.  **Product Groups:** Links Group Number to Group Name.

# Create Product Data Frame
product_data = cleaned_pick_data[['product_id', 'warehouse_section', 'quantity_unit']].copy()

# Map product group numbers
product_data['product_group_num'] = product_data['product_id'].map(
    cleaned_product_df.set_index('product_id')['product_group']
)
product_data = product_data.drop_duplicates()

# Create Product Group Dimension Table
def create_product_groups(df):
    df = df.drop(['product_id', 'product_description'], axis=1)
    df = df.dropna().drop_duplicates()

    # Split '35_Leuchten' into '35' and 'Leuchten'
    df['product_group_num'] = df['product_group'].apply(lambda x: x.split('_')[0])
    df['product_group_name'] = df['product_group'].apply(lambda x: x.split('_')[1])

    df = df.drop('product_group', axis=1)
    df = df.sort_values(by='product_group_num')
    return df

## 6. Date Dimension Table
#Create a standard date table derived from order summaries.

def create_date_table(df):
    dates = df['date'].unique()
    date_table = pd.DataFrame(pd.to_datetime(dates), columns=['date'])

    date_table['year'] = date_table['date'].dt.year
    date_table['month'] = date_table['date'].dt.month
    date_table['day'] = date_table['date'].dt.day
    date_table['day_of_week'] = date_table['date'].dt.day_name()

    return date_table

date_table = create_date_table(final_order_data)

## 7. Market Basket Analysis
# Identify top 10 most frequently bought product pairs.
comb_counter = Counter()

# Pull only the columns needed to minimize memory usage
market_basket_df = pd.read_sql(
    "SELECT updated_order_number, product_id FROM pick_data_processed", 
    engine
)

order_groups = market_basket_df.groupby('updated_order_number')['product_id'].apply(list)
for products in order_groups:
    if len(products) > 1:
        comb_counter.update(combinations(sorted(set(products)), 2))

## 8. Load to MySQL

final_order_data.to_sql('final_order_summary', engine, if_exists='replace', index=False)
date_table.to_sql('dim_date', engine, if_exists='replace', index=False)
top_combos.to_sql('bestselling_pairs', engine, if_exists='replace', index=False)

print("ETL Process Complete: Data extracted from and loaded back to MySQL.")

# to prevent execution when imported

if __name__ == "__main__":

    print("This script is intended to be imported as a module, not run directly.")