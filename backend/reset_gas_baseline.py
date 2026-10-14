"""Reset gas baseline learning for one device without deleting history."""

import sys

from app.database import get_db_connection
from app.init_db import init_db
from app.services.state_reset import reset_gas_state_for_device


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit("Usage: python reset_gas_baseline.py DEVICE_ID")
    init_db()
    connection = get_db_connection()
    try:
        connection.execute("BEGIN")
        count = reset_gas_state_for_device(connection, sys.argv[1].strip())
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(f"Reset gas baseline for {sys.argv[1].strip()}: {count} context(s)")
