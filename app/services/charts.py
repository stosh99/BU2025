"""Chart generation helpers using matplotlib."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import pandas as pd


def generate_player_chart(stats, columns, ylabel, title, ma_label,
                          y_min=None, y_max=None, window=7):
    """Generate a line chart with moving average for player stats over time.

    Args:
        stats: list of (Date, value) tuples from a query
        columns: column names for the DataFrame, e.g. ['Date', 'RC']
        ylabel: y-axis label
        title: chart title
        ma_label: label for the moving average line
        y_min: optional y-axis minimum
        y_max: optional y-axis maximum
        window: rolling average window size

    Returns:
        Base64-encoded PNG string, or None if stats is empty.
    """
    if not stats:
        return None

    stat_col = columns[1]
    df = pd.DataFrame(stats, columns=columns)
    df['Date'] = pd.to_datetime(df['Date'])
    df[stat_col] = pd.to_numeric(df[stat_col])
    df = df.sort_values(by='Date')
    ma_col = f'{stat_col}_MA'
    df[ma_col] = df[stat_col].rolling(window=window, min_periods=1).mean()

    plt.figure(figsize=(10, 6))
    plt.plot(df['Date'], df[stat_col], marker='o', linestyle='-', label=stat_col)
    plt.plot(df['Date'], df[ma_col], marker='', linestyle='--', label=ma_label)
    plt.xlabel('Date')
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.gcf().autofmt_xdate()

    if y_min is not None or y_max is not None:
        plt.ylim(bottom=y_min, top=y_max)

    img = BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close()
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()
