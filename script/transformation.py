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

# ## 2. Load Raw Data
# Load the original `pick_data` CSV file into a pandas DataFrame.
# *Note: Ensure the file path is correct before running.*

filename = r"C:\Users\LindseyBuss\Documents\OBETA_Project\003 pick_data.csv"
column_names = [
    'product_id', 'warehouse_section', 'origin', 'order_number',
    'position_in_order', 'pick_volume', 'quantity_unit', 'date'
]
data_types = {
    'product_id': 'string',
    'warehouse_section': 'category',
    'origin': 'category',
    'order_number': 'string',
    'position_in_order':'int64',
    'pick_volume': 'int64',
    'quantity_unit': 'string',
    'date': 'string'
}

# Read CSV with defined headers and types
original_pick_data_df = pd.read_csv(
    filename,
    names=column_names,
    header=None,
    dtype=data_types,
    parse_dates=['date']
)
print(original_pick_data_df.head()) 

# ## 3. Pick Data Transformation
# ### 3.1 pick_data table basic transformations

# Add unique sequential pick IDs
original_pick_data_df['pick_id'] = range(1, len(original_pick_data_df) + 1)

# Extract year of order to create new unique order IDs
original_pick_data_df['year_of_order'] = original_pick_data_df['date'].dt.year.astype(str)

# Concatenate the original order number with the year (e.g., "07055448-2017")
original_pick_data_df['updated_order_number'] = (
    original_pick_data_df[['order_number', 'year_of_order']]
    .astype(str)
    .agg('-'.join, axis=1)
)

# Drop redundant columns
original_pick_data_df = original_pick_data_df.drop(columns='order_number')

# Drop NaNs and Duplicates
original_pick_data_df = original_pick_data_df.dropna()
original_pick_data_df = original_pick_data_df.drop_duplicates()

# Filter out zero-volume picks
original_pick_data_df = original_pick_data_df[original_pick_data_df['pick_volume'] != 0]

cleaned_pick_data = original_pick_data_df.copy() #create a copy for further cleaning

# cleaned_pick_data.to_parquet('cleaned_pick_data.parquet')

# ### 3.3 Outlier Detection
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

# **Apply Outlier Detection:** Run the function on the cleaned pick data

pick_data_with_outliers = flag_outliers_by_unit(
    cleaned_pick_data,
    value_col="pick_volume",
    group_col="quantity_unit",
    method="zscore",
    threshold=3.0,
)
# Update the main dataframe reference
cleaned_pick_data = pick_data_with_outliers

# cleaned_pick_data.to_csv('cleaned_pick_data.csv')

# ## 4. Order Summaries
# ### 4.1 Define Aggregation Logic
# Create a function to summarize data at the order level. This calculates complexity metrics (number of picks, sections, products) and fulfillment time.

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

    # Calculate time to fulfill in minutes
    order_summary_data['time_to_fulfil'] = (
        order_summary_data['time_of_last_pick'] - order_summary_data['time_of_first_pick']
    ) / np.timedelta64(1, 'm')

    order_summary_data['date'] = order_summary_data['time_of_first_pick'].dt.date

    # Clean zero durations and impute missing values based on group means
    order_summary_data['time_to_fulfil'] = order_summary_data['time_to_fulfil'].replace(0, np.nan)
    group_means = order_summary_data.groupby('num_picks')['time_to_fulfil'].transform('mean')
    order_summary_data['time_to_fulfil'] = order_summary_data['time_to_fulfil'].fillna(group_means)

    # Specific imputation for single-pick orders (half the average of 2-pick orders)
    # Note: Hardcoded value based on previous analysis
    order_summary_data['time_to_fulfil'] = order_summary_data['time_to_fulfil'].fillna(30.496420)

    return order_summary_data

# ### 4.2 Generate Summaries
# Process orders year-by-year for efficiency and concatenate.

years = cleaned_pick_data['year_of_order'].unique()
order_summaries_by_year = []

for year in years:
    df_subset = cleaned_pick_data[cleaned_pick_data['year_of_order'] == year]
    summarized_year = summarize_year(df_subset)
    order_summaries_by_year.append(summarized_year)

final_order_data = pd.concat(order_summaries_by_year)

# final_order_data.to_parquet('final_order_summary.parquet')

# ## 5. Product Data Transformation
# ### 5.1 Load and Clean Product Data

# Update path as needed
filename = r"C:\Users\LindseyBuss\Documents\OBETA_Project\002 product_data.csv"

column_names = ['product_id', 'product_description', 'product_group']
data_types = {
    'product_id': 'string',
    'product_description': 'string',
    'product_group': 'category'
}

# Use Latin-1 encoding for special characters
product_groups_df = pd.read_csv(
    filename,
    names=column_names,
    header=None,
    dtype=data_types,
    encoding='latin-1'
)

def clean_products(df):
    df = df.dropna()
    df = df.drop_duplicates()
    # Extract only the group number prefix (e.g., '35' from '35_Leuchten')
    df['product_group'] = df['product_group'].apply(lambda x: x.split('_')[0])
    return df

cleaned_product_df = clean_products(product_groups_df)


# ### 5.2 Create Product Dimension Tables
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

product_groups = create_product_groups(product_groups_df)


# ## 6. Date Dimension Table
# Create a standard date table derived from order summaries.

def create_date_table(df):
    dates = df['date'].unique()
    date_table = pd.DataFrame(pd.to_datetime(dates), columns=['date'])

    date_table['year'] = date_table['date'].dt.year
    date_table['month'] = date_table['date'].dt.month
    date_table['day'] = date_table['date'].dt.day
    date_table['day_of_week'] = date_table['date'].dt.day_name()

    return date_table

date_table = create_date_table(final_order_data)


# ## 7. Market Basket Analysis (Bestsellers)


# Reading in chunks to handle large CSV file efficiently
chunk_size = 200_000
comb_counter = Counter()

filename = r"C:\Users\LindseyBuss\Documents\OBETA_Project\cleaned_pick_data.csv"
column_names = ['product_id', 'warehouse_section', 'updated_order_number', 'quantity_unit']
data_types = {
    'product_id': 'string',
    'warehouse_section': 'category',
    'updated_order_number': 'string',
    'quantity_unit': 'string',
}

# Iterate through chunks
for chunk in pd.read_csv(filename, chunksize=chunk_size, usecols=column_names, dtype=data_types):
    # Group products by order_id
    order_groups = chunk.groupby('updated_order_number')['product_id'].apply(list)

    # Count combinations in each order
    for products in order_groups:
        if len(products) > 1:
            # Sort products to ensure (A, B) is treated same as (B, A)
            comb_counter.update(combinations(sorted(set(products)), 2))

# Get top 25 combinations
top_combos = pd.DataFrame(
    [(prod1, prod2, count) for (prod1, prod2), count in comb_counter.most_common(25)],
    columns=['product_1', 'product_2', 'count']
)

top_combos['bestselling_pair_ranking'] = top_combos.index + 1
print(top_combos)

# ### 7.1 Enrich Bestseller Data
# Create a list of individual bestselling products and merge with product details (Warehouse Section, Group, Unit).

# Create a single column list of all products in the top pairs
bestsellers_list = top_combos['product_1'].to_list() + top_combos['product_2'].to_list()
bestsellers = pd.DataFrame(bestsellers_list, columns=['product_id'])

# Merge with product details
# IMPROVEMENT: Use 'left' join to keep all bestsellers, even if details are missing
bestsellers_with_product_info = pd.merge(
    bestsellers,
    product_data,
    on='product_id',
    how='left'
)

# Drop duplicates if a product appears in multiple pairs
bestsellers_with_product_info = bestsellers_with_product_info.drop_duplicates().reset_index(drop=True)

#print(bestsellers_with_product_info.head(20))
