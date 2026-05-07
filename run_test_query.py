import sqlite3

DB='central.db'

print('Opening database:',DB)
conn=sqlite3.connect(DB)
cur=conn.cursor()
try:
    cur.execute("SELECT id, server_id, command, status, created_at FROM remote_command WHERE server_id=? AND status=? ORDER BY created_at ASC LIMIT 5",(2,'pending'))
    rows=cur.fetchall()
    print('Query returned',len(rows),'rows')
    for r in rows:
        print(r)
except Exception as e:
    print('ERROR running query:',e)
finally:
    conn.close()
