import psycopg

conn = psycopg.connect(
    host="207.246.116.8",
    port=5432,
    dbname="vigilancia",
    user="pedro",
    password="123456"
)

cur = conn.cursor()
cur.execute("SELECT NOW();")
print(cur.fetchone())

cur.close()
conn.close()