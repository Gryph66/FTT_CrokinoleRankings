import sqlite3

def add_column():
    conn = sqlite3.connect('public_data.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE points_parameters ADD COLUMN doubles_weight_high FLOAT DEFAULT 0.65;")
        conn.commit()
        print("✅ Successfully added column doubles_weight_high to points_parameters")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("⚠️ Column already exists")
        else:
            print(f"❌ Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_column()
