# Flag outliers in a DataFrame column per group defined by another column.
import pandas as pd
import numpy as np
import logging
from typing import Optional, Literal

logger = logging.getLogger(__name__)
#=========================================
# Define the main function
def flag_outliers(
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

    Parameters
    ----------
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
        Degrees of freedom for std in zscore method.
    min_group_size : int
        Minimum group size to compute outliers. Smaller groups are marked as non-outliers.
    separate_sides : bool
        If True, adds two columns: lower/upper outliers (instead of a single boolean).
    flag_col : str, optional
        Name of the output flag column when separate_sides=False.
        Defaults to 'outlier_by_{group_col}'.

    Returns
    -------
    pd.DataFrame
        Copy of df with added outlier flag column(s), computed per group.
        NaN values in value_col are treated as non-outliers.

    """

    # Input validation
    if value_col not in df.columns:
        raise ValueError(f"Column '{value_col}' not found in DataFrame")
    if group_col not in df.columns:
        raise ValueError(f"Column '{group_col}' not found in DataFrame")
    if threshold is not None and threshold <= 0:
        raise ValueError(f"threshold must be positive, got {threshold}")
    if method not in ("zscore", "modified"):
        raise ValueError(f"method must be 'zscore' or 'modified', got '{method}'")

    if threshold is None:
        threshold = 3.0 if method == "zscore" else 3.5
    if flag_col is None and not separate_sides:
        flag_col = f"outlier_by_{group_col}"

    out = df.copy()

    # Ensure numeric dtype (will convert errors to NaN)
    x = pd.to_numeric(out[value_col], errors="coerce")
    logger.info(f"Processing {value_col} with method={method}, threshold={threshold}, group_col={group_col}")

    def compute_group_flags(group_values: pd.Series) -> pd.Series:
        """
        Compute outlier flags for a single group.
        ----------
        Parameters
            group_values : pd.Series
            Numeric values for one group.
        ----------
        Returns
        pd.Series or pd.DataFrame
            Boolean series/dataframe indicating outliers for this group.
        """
        # Respect minimum group size
        valid = group_values.dropna()
        if valid.size < min_group_size:
            logger.warning(f"Group size {valid.size} < min_group_size {min_group_size}; marking as non-outliers")
            if separate_sides:
                return pd.DataFrame(
                    {"is_lower_outlier": False, "is_upper_outlier": False},
                    index=group_values.index
                )
            else:
                return pd.Series(False, index=group_values.index, name=flag_col)

        if method == "zscore":
            mean = valid.mean()
            std = valid.std(ddof=ddof)
            if std == 0 or np.isnan(std):
                logger.warning("Standard deviation is zero; marking all as non-outliers")
                z_scores = pd.Series(0.0, index=group_values.index)
            else:
                z_scores = (group_values - mean) / std
        else:  # method == "modified"
            med = valid.median()
            mad = (valid - med).abs().median()
            # 0.6745 is the constant to scale MAD to match std for normal distribution
            if mad == 0 or np.isnan(mad):
                logger.warning("Median Absolute Deviation is zero; marking all as non-outliers")
                z_scores = pd.Series(0.0, index=group_values.index)
            else:
                z_scores = 0.6745 * (group_values - med) / mad

        # Build masks; treat NaNs as non-outliers
        if separate_sides:
            return pd.DataFrame(
                {
                    "is_lower_outlier": z_scores.lt(-threshold).fillna(False),
                    "is_upper_outlier": z_scores.gt(threshold).fillna(False)
                },
                index=group_values.index
            )
        else:
            return pd.Series(z_scores.abs().gt(threshold).fillna(False), index=group_values.index, name=flag_col)

    # Use transform for better performance and alignment
    if separate_sides:
        # For multiple output columns, we need to use apply and handle index carefully
        flags = x.groupby(out[group_col], dropna=False).apply(compute_group_flags)
        # Reset index to align with original dataframe
        flags = flags.reset_index(drop=True)
        out["is_lower_outlier"] = flags["is_lower_outlier"]
        out["is_upper_outlier"] = flags["is_upper_outlier"]
        logger.info(f"Flagged {flags['is_lower_outlier'].sum()} lower and {flags['is_upper_outlier'].sum()} upper outliers")
    else:
        # Use transform for single output column (more efficient)
        out[flag_col] = x.groupby(out[group_col], dropna=False).transform(compute_group_flags)
        logger.info(f"Flagged {out[flag_col].sum()} outliers in total")

    return out

if __name__ == "__main__":
    # Configure logging for demonstration
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Example usage with test data
    data = {
        "quantity_unit": ["kg"] * 8 + ["lb"] * 8,
        "value": [
            # kg group: normal values around 10, with some outliers
            10, 11, 9.5, 12, 100, 11.2, 10.8, -50,
            # lb group: normal values around 5, with some outliers
            5, 6, 4.8, 5.5, 50, 5.2, 4.9, -20
        ]
    }
    df = pd.DataFrame(data)
    result = flag_outliers(
        df,
        value_col="value",
        group_col="quantity_unit",
        method="zscore",
        threshold=2.5,
        separate_sides=False,
    )
    print(result)
    print("\nOutlier summary by unit:")
    print(result.groupby("quantity_unit")["outlier_by_quantity_unit"].sum())
    """
    Example Output:
         quantity_unit  value  outlier_by_quantity_unit
    0             kg     10                     False
    1             kg     11                     False
    2             kg    100                      True
    3             lb      5                     False
    4             lb      6                     False
    5             lb     50                      True
    """
    
    print("\n=== Example 2: Modified Z-score method (separate sides) ===")
    result2 = flag_outliers(
        df,
        value_col="value",
        group_col="quantity_unit",
        method="modified",
        threshold=3.0,
        separate_sides=True,
    )
    print(result2)
    print("\nOutlier summary by unit:")
    print(result2.groupby("quantity_unit").agg({"is_lower_outlier": "sum", "is_upper_outlier": "sum"}))
