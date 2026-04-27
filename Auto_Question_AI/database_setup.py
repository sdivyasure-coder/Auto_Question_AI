import sqlite3
import pandas as pd
import os

DB_FILE = "users.db"
CSV_FILE = "questionbank.csv"

def init_db():
    print(f"Initializing database: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # 1. Users Table (Existing structure + enhancement if needed)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    # 2. Questions Table (Enhanced for ML)
    # difficulty: Easy, Medium, Hard (Inferred initially, adjustable by Admin/ML)
    # usage_freq: How many times this question has been selected
    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            chapter INTEGER,
            question_text TEXT,
            mark INTEGER,
            difficulty TEXT,
            question_type TEXT,
            usage_freq INTEGER DEFAULT 0,
            last_used TIMESTAMP
        )
    """)

    # 3. Generated Papers Table (History)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS generated_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_name TEXT,
            subject TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT
        )
    """)

    conn.commit()
    
    # Check if we need to migrate CSV data
    cur.execute("SELECT count(*) FROM questions")
    count = cur.fetchone()[0]
    
    if count == 0 and os.path.exists(CSV_FILE):
        print("Migrating data from CSV to SQLite...")
        try:
            df = pd.read_csv(CSV_FILE, engine="python", on_bad_lines="skip")
            
            # Data Cleaning & Feature Engineering for Migration
            # We infer 'difficulty' based on 'mark' as a starting point for the ML model
            # 2 marks -> Easy, 7 marks -> Medium, 15 marks -> Hard
            def infer_difficulty(mark):
                if mark <= 2: return "Easy"
                elif mark <= 7: return "Medium"
                else: return "Hard"

            # We infer 'question_type'
            # Typically 2 marks are Short Answer, others are Descriptive
            def infer_type(mark):
                if mark <= 2: return "Short"
                else: return "Descriptive"

            for _, row in df.iterrows():
                difficulty = infer_difficulty(row['mark'])
                q_type = infer_type(row['mark'])
                
                cur.execute("""
                    INSERT INTO questions (subject, chapter, question_text, mark, difficulty, question_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (row['subject'], row['chapter'], row['question'], row['mark'], difficulty, q_type))
            
            conn.commit()
            print(f"Successfully migrated {len(df)} questions.")
        except Exception as e:
            print(f"Error during migration: {e}")
    else:
        print("Database already contains data or CSV not found. Skipping migration.")

    # Create default users if they don't exist
    cur.execute("SELECT * FROM users WHERE username='professor1'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("professor1", "prof123", "professor"))
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("student1", "stud123", "student"))
        conn.commit()
        print("Default users created.")

    conn.close()
    print("Database setup complete.")

if __name__ == "__main__":
    init_db()
