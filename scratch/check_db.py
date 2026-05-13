
import sqlite3
import json

db_path = "data/lerh.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

user_id = "8b1dc71ec647"

print(f"--- User {user_id} ---")
user = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
if user:
    print(dict(user))
else:
    print("User not found")

print(f"\n--- CVs for User {user_id} ---")
cvs = cursor.execute("SELECT * FROM cvs WHERE user_id = ?", (user_id,)).fetchall()
for cv in cvs:
    print(dict(cv))

print(f"\n--- Jobs mentioned in CVs ---")
for cv in cvs:
    job_id = cv['job_id']
    if job_id:
        job = cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job:
            print(f"Job ID: {job_id}")
            print(dict(job))

print(f"\n--- Last 5 Messages for User {user_id} ---")
messages = cursor.execute("SELECT * FROM messages WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (user_id,)).fetchall()
for msg in messages:
    print(dict(msg))

conn.close()
