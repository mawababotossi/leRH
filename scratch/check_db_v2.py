import sqlite3

db_path = "data/lerh.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

user_id = "8b1dc71ec647"

print(f"--- User {user_id} ---")
user = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
if user:
    u = dict(user)
    # Hide potentially sensitive IDs but show profile
    print(f"Name: {u['name']}")
    print(f"Activity: {u['activity']}")
    print(f"Country: {u['country']}")
    print(f"City: {u['city']}")
    print(f"Diploma: {u['diploma']}")
    print(f"Skills: {u['skills']}")

print(f"\n--- CVs for User {user_id} ---")
cvs = cursor.execute("SELECT * FROM cvs WHERE user_id = ?", (user_id,)).fetchall()
for cv in cvs:
    c = dict(cv)
    print(f"CV ID: {c['id']}, Job ID: {c['job_id']}, Type: {c['cv_type']}, File: {c['file_path']}")

print("\n--- Jobs mentioned ---")
for cv in cvs:
    job_id = cv["job_id"]
    if job_id:
        job = cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job:
            j = dict(job)
            print(f"Job ID: {job_id}, Title: {j['title']}, Company: {j['company']}")

conn.close()
