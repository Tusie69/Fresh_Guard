from app.database import get_db_connection
from app.services.rule_provider import seed_default_rules


def init_db():
    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            received_at TEXT NULL,
            delivery_delay_seconds REAL NULL,
            ingest_status TEXT NULL,
            temperature_c REAL,
            humidity_pct REAL,
            gas_raw INTEGER,
            door_open INTEGER NOT NULL,
            open_duration_seconds INTEGER NOT NULL DEFAULT 0,
            food_id TEXT NULL,
            device_reading_id TEXT NULL,
            freshness_status TEXT NULL,
            freshness_reason TEXT NULL,
            freshness_evaluated_at TEXT NULL,
            gas_anomaly_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Upgrade databases created before open_duration_seconds was added.
    reading_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(sensor_readings)")
    }
    if "open_duration_seconds" not in reading_columns:
        connection.execute(
            "ALTER TABLE sensor_readings "
            "ADD COLUMN open_duration_seconds INTEGER NOT NULL DEFAULT 0"
        )
    if "food_id" not in reading_columns:
        connection.execute(
            "ALTER TABLE sensor_readings ADD COLUMN food_id TEXT NULL"
        )
    for column, declaration in (
        ("received_at", "TEXT NULL"),
        ("delivery_delay_seconds", "REAL NULL"),
        ("ingest_status", "TEXT NULL"),
        ("device_reading_id", "TEXT NULL"),
        ("freshness_status", "TEXT NULL"),
        ("freshness_reason", "TEXT NULL"),
        ("freshness_evaluated_at", "TEXT NULL"),
        ("gas_anomaly_active", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in reading_columns:
            connection.execute(
                f"ALTER TABLE sensor_readings ADD COLUMN {column} {declaration}"
            )

    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "idx_sensor_readings_device_reading_id "
        "ON sensor_readings (device_id, device_reading_id)"
    )
    # A few very old databases contain only the original id/device_id pair.
    # Keep init_db backward-compatible for those schemas; the normal schema
    # always has timestamp and receives the timeline index.
    if "timestamp" in reading_columns:
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_timestamp "
            "ON sensor_readings (device_id, timestamp DESC, id DESC)"
        )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS food_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_id TEXT UNIQUE NOT NULL,
            food_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity REAL,
            inserted_at TEXT NOT NULL,
            manufacture_date TEXT,
            expiry_date TEXT,
            storage_location TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS gas_anomaly_state (
            device_id TEXT NOT NULL,
            food_id TEXT NOT NULL DEFAULT '',
            baseline REAL NULL,
            baseline_sample_count INTEGER NOT NULL DEFAULT 0,
            baseline_sum REAL NOT NULL DEFAULT 0,
            consecutive_anomaly_count INTEGER NOT NULL DEFAULT 0,
            anomaly_active INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (device_id, food_id)
        )
    """)

    # Keep the original state table shape compatible with older tooling that
    # inserts its seven legacy columns positionally. Lifecycle metadata lives
    # in a side table so migration never changes historical state semantics.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS gas_baseline_lifecycle (
            device_id TEXT NOT NULL,
            food_id TEXT NOT NULL DEFAULT '',
            baseline_status TEXT NOT NULL DEFAULT 'WARMING_UP',
            warmup_started_at TEXT NULL,
            stability_values TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (device_id, food_id)
        )
    """)

    active_table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='active_foods'"
    ).fetchone()
    active_columns = (
        {row[1] for row in connection.execute("PRAGMA table_info(active_foods)")}
        if active_table else set()
    )
    if active_table and "device_id" not in active_columns:
        # Preserve legacy global activations as device-less compatibility rows.
        connection.execute("ALTER TABLE active_foods RENAME TO active_foods_legacy")
        active_table = None
    if not active_table:
        connection.execute("""
            CREATE TABLE active_foods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NULL,
                food_id TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                FOREIGN KEY (food_id) REFERENCES food_items(food_id)
            )
        """)
        if active_columns:
            connection.execute("""
                INSERT INTO active_foods (device_id, food_id, activated_at)
                SELECT NULL, food_id, activated_at FROM active_foods_legacy
            """)
            connection.execute("DROP TABLE active_foods_legacy")
    # A device can monitor multiple foods in the same fridge. Older versions
    # used a partial UNIQUE index here, which made adding a new food replace
    # the previous active mapping. Migrate that index to a normal lookup index.
    connection.execute("DROP INDEX IF EXISTS idx_active_foods_device")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_active_foods_device "
        "ON active_foods(device_id)"
    )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS food_freshness_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reading_id INTEGER NOT NULL,
            food_id TEXT NOT NULL,
            freshness_status TEXT NOT NULL,
            freshness_reason TEXT NOT NULL,
            evaluated_at TEXT NOT NULL,
            UNIQUE (reading_id, food_id),
            FOREIGN KEY (reading_id) REFERENCES sensor_readings(id),
            FOREIGN KEY (food_id) REFERENCES food_items(food_id)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS notification_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT NOT NULL UNIQUE,
            notification_type TEXT NOT NULL CHECK (
                notification_type IN (
                    'FOOD_USE_SOON', 'FOOD_CHECK_FOOD', 'FOOD_RECOVERED', 'FOOD_ADDED',
                    'DEVICE_FRESH', 'DEVICE_USE_SOON', 'DEVICE_CHECK_FOOD'
                )
            ),
            food_id TEXT NULL,
            reading_id INTEGER NULL,
            payload_json TEXT NOT NULL,
            delivery_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
                delivery_status IN ('PENDING', 'DELIVERED', 'FAILED')
            ),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NULL,
            created_at TEXT NOT NULL,
            delivered_at TEXT NULL,
            claim_token TEXT NULL,
            lease_until TEXT NULL,
            FOREIGN KEY (reading_id) REFERENCES sensor_readings(id),
            FOREIGN KEY (food_id) REFERENCES food_items(food_id)
        )
    """)

    outbox_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(notification_outbox)")
    }
    for column in ("claim_token", "lease_until"):
        if column not in outbox_columns:
            connection.execute(f"ALTER TABLE notification_outbox ADD COLUMN {column} TEXT NULL")

    # SQLite cannot alter a CHECK constraint in place. Rebuild only legacy
    # outboxes that predate device-level notification types, preserving rows.
    outbox_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='notification_outbox'"
    ).fetchone()[0] or ""
    if "DEVICE_FRESH" not in outbox_sql or "FOOD_ADDED" not in outbox_sql:
        connection.execute("ALTER TABLE notification_outbox RENAME TO notification_outbox_legacy")
        connection.execute("""
            CREATE TABLE notification_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL UNIQUE,
                notification_type TEXT NOT NULL CHECK (
                    notification_type IN (
                        'FOOD_USE_SOON', 'FOOD_CHECK_FOOD', 'FOOD_RECOVERED', 'FOOD_ADDED',
                        'DEVICE_FRESH', 'DEVICE_USE_SOON', 'DEVICE_CHECK_FOOD'
                    )
                ),
                food_id TEXT NULL,
                reading_id INTEGER NULL,
                payload_json TEXT NOT NULL,
                delivery_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
                    delivery_status IN ('PENDING', 'DELIVERED', 'FAILED')
                ),
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NULL,
                created_at TEXT NOT NULL,
                delivered_at TEXT NULL,
                claim_token TEXT NULL,
                lease_until TEXT NULL,
                FOREIGN KEY (reading_id) REFERENCES sensor_readings(id),
                FOREIGN KEY (food_id) REFERENCES food_items(food_id)
            )
        """)
        connection.execute("""
            INSERT INTO notification_outbox (
                id, event_key, notification_type, food_id, reading_id,
                payload_json, delivery_status, attempt_count, last_error,
                created_at, delivered_at, claim_token, lease_until
            )
            SELECT id, event_key, notification_type, food_id, reading_id,
                   payload_json, delivery_status, attempt_count, last_error,
                   created_at, delivered_at, claim_token, lease_until
            FROM notification_outbox_legacy
        """)
        connection.execute("DROP TABLE notification_outbox_legacy")

    connection.execute("""
        CREATE TABLE IF NOT EXISTS device_freshness_snapshots (
            device_id TEXT PRIMARY KEY,
            freshness_status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS temperature_exposure_state (
            device_id TEXT NOT NULL,
            food_id TEXT NOT NULL DEFAULT '',
            exposure_seconds REAL NOT NULL DEFAULT 0,
            exposure_active INTEGER NOT NULL DEFAULT 0,
            exposure_exceeded INTEGER NOT NULL DEFAULT 0,
            last_valid_temperature_timestamp TEXT NULL,
            continuity_broken INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (device_id, food_id)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS sensor_fault_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            food_id TEXT NULL,
            sensor_name TEXT NOT NULL,
            fault_active INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
    """)
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sensor_fault_logical_key "
        "ON sensor_fault_state (device_id, COALESCE(food_id, ''), sensor_name)"
    )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT,
            door_open INTEGER NOT NULL,
            open_duration_seconds INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('USER', 'ADMIN')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS freshness_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_key TEXT NOT NULL UNIQUE,
            rule_value TEXT NOT NULL,
            value_type TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_by_user_id INTEGER NULL
        )
    """)
    seed_default_rules(connection)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS freshness_rule_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER NOT NULL,
            actor_username TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            rule_key TEXT NOT NULL,
            old_value TEXT NOT NULL,
            new_value TEXT NOT NULL,
            value_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS user_management_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER NOT NULL,
            actor_username TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            target_user_id INTEGER NOT NULL,
            target_username TEXT NOT NULL,
            action TEXT NOT NULL,
            old_value TEXT NULL,
            new_value TEXT NULL,
            reason TEXT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
