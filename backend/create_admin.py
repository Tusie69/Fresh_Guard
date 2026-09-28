"""Create a local FreshGuard ADMIN without storing plaintext credentials."""

import getpass
import sys

from app.database import get_db_connection
from app.init_db import init_db
from app.services.auth import create_user


def main():
    init_db()
    username = input("Admin username: ").strip()
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    connection = get_db_connection()
    try:
        create_user(connection, username, password, "ADMIN")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(f"Created ADMIN user: {username}")


if __name__ == "__main__":
    sys.exit(main())
