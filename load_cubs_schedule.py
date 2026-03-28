"""One-time utility: load CubsSchedule2026.xlsx into the CubsSchedule2025 table."""

import pandas as pd
from app import create_app
from app.extensions import db

app = create_app()

df = pd.read_excel('CubsSchedule2026.xlsx')

# Map spreadsheet columns to table columns
df = df.rename(columns={'START DATE': 'Date'})

# Convert Date to string to match the text column type
df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')

# Convert NaN to None for nullable bigint
import numpy as np
df = df.replace({np.nan: None})

with app.app_context():
    rows = df.to_dict(orient='records')
    for row in rows:
        db.session.execute(
            db.text('INSERT INTO CubsSchedule2025 (Date, Games, Xfactor) VALUES (:Date, :Games, :Xfactor)'),
            row
        )
    db.session.commit()
    print(f"Inserted {len(rows)} rows into CubsSchedule2025")
