import sqlite3
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DB_PATH
from datetime import date

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("DELETE FROM schedule WHERE date >= ?", (str(date.today()),))
conn.commit()
conn.close()
