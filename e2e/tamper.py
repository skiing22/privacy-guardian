"""J4: change one audit record directly in the database file, as an attacker with disk
access would. Drops the append-only trigger first (that is what such an attacker does)."""

import sqlite3
import sys

db, seq = sys.argv[1], int(sys.argv[2])
c = sqlite3.connect(db)
c.execute("DROP TRIGGER IF EXISTS audit_no_update")
c.execute("UPDATE audit_log SET payload = '{\"edited\": true}' WHERE seq = ?", (seq,))
c.commit()
c.close()
