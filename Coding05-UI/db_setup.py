import sqlite3

# Connects to the database file (creates it if it does not exist)
with sqlite3.connect("receipt_agent.db") as connection:
    cursor = connection.cursor()
    
    # Create a table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchase (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            item TEXT NOT NULL,
            store TEXT NOT NULL,
            price INTEGER NOT NULL
        )
    ''')
    
    print("Database and table successfully set up!")