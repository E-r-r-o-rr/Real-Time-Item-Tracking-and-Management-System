# view_db.py
import sqlite3
from tabulate import tabulate  # for nicer console output

# Connect to the SQLite file (orders.db) in the current folder
conn = sqlite3.connect("orders.db")
cursor = conn.cursor()

# Fetch column names
cursor.execute("PRAGMA table_info(orders);")
cols = [row[1] for row in cursor.fetchall()]

# Fetch all rows
cursor.execute("SELECT * FROM orders;")
rows = cursor.fetchall()

# Print in a table format
print(tabulate(rows, headers=cols, tablefmt="github"))

conn.close()
