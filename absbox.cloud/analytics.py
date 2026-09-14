import numpy as np
import pandas as pd

def calcWAL(dates, balances):
    """
    Calculate the Weighted Average Life (WAL) of a bond.

    Args:
        dates (list or array-like): List of payment dates (as datetime or pandas.Timestamp).
        balances (list or array-like): List of principal payments (same length as dates).

    Returns:
        float: Weighted Average Life in years.
    """
    if len(dates) != len(balances):
        raise ValueError("dates and balances must have the same length")
    if sum(balances) == 0:
        return 0.0
    #print("Calculating WAL for dates:", dates, "and balances:", balances)
    # Convert dates to pandas Timestamps
    dates = pd.to_datetime(dates)
    # Assume the first date is the settlement date
    settlement = dates.iloc[0] if isinstance(dates, pd.Series) else dates[0]
    # Calculate time in years from settlement for each payment
    years = (dates - settlement).days / 365.25
    # Calculate WAL
    wal = np.sum(np.array(balances) * years) / np.sum(balances)
    return wal