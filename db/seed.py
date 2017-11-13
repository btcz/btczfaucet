import sqlite3
db = sqlite3.connect('faucet_db')

cursor = db.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS donations(
        id INTEGER PRIMARY KEY, 
        ip TEXT,
        wallet TEXT,
        donation REAL,
        time INTEGER)
''')
db.commit()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS total(
        amount REAL)
''')
db.commit()

db.execute("insert into total values (0.0)")
db.commit()

db.close()
