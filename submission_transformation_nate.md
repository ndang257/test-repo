# Obeta Data Transformation Process

This notebook outlines the data transformation process used on two datasets provided by Obeta, `pick_data`  and `product_data` .
1. **Pick Data**: Transactional data regarding warehouse picks.
2. **Product Data**: Descriptive data regarding product hierarchies.
**Key steps include:**
* Generating unique identifiers for orders and picks.
* Cleaning nulls, duplicates, and invalid entries.
* Flagging statistical outliers in pick volumes.
* Aggregating data to summarize order fulfilment times.
* Creating dimension tables for Products and Dates.

The transformation code was written by Lindsey and this notebook is edited by Nate.

## 1. Setup and Imports
Import the necessary libraries for data manipulation and statistical analysis.

```python
import pandas as pd
import numpy as np
from scipy import stats
from typing import Optional, Literal
```

## 2. Load Raw Data
Load the original `pick_data` CSV file into a pandas DataFrame.
*Note: Ensure the file path is correct before running.*

```python
# Adjust the path name as needed to pull in the original CSV file.

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

# Display the first few rows of the DataFrame if needed
print(original_pick_data_df.head())
```

## 3. Pick Data Transformation
### 3.1 pick_data table basic transformations
The few basic transformations are:
- generating unique order numbers by concatenate the existing order numbers with their corresponding year
- Drop null values, duplicates, original order number, picks with a volume of zero

```python
# Extract year of order to create new unique order IDs.

original_pick_data_df['year_of_order'] = original_pick_data_df['date'].dt.year.astype(str  

original_pick_data_df['updated_order_number'] = original_pick_data_df[['order_number', 'year_of_order']].astype(str).agg('-'.join, axis=1)

original_pick_data_df = original_pick_data_df.drop(columns='order_number')
original_pick_data_df = original_pick_data_df.dropna()
original_pick_data_df = original_pick_data_df.drop_duplicates()

original_pick_data_df = original_pick_data_df[original_pick_data_df['pick_volume'] != 0]

cleaned_pick_data = original_pick_data_df
print(original_pick_data_df.head())

# Export the cleaned pick data without outliers if desired.
# cleaned_pick_data.to_parquet()
```
