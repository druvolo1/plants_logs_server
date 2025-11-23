import sqlite3

conn = sqlite3.connect('data/herb_nerdz.db')
cursor = conn.cursor()

cursor.execute('SELECT device_id, name, device_type, scope, is_online, last_seen FROM devices WHERE device_type="environmental"')

print('Environmental Sensors:')
for row in cursor.fetchall():
    print(f'  Device ID: {row[0]}')
    print(f'  Name: {row[1]}')
    print(f'  Type: {row[2]}')
    print(f'  Scope: {row[3]}')
    print(f'  Online: {row[4]}')
    print(f'  Last Seen: {row[5]}')
    print()

conn.close()
