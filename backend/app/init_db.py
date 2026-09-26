from app.database import get_db_connection


def init_db():
    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
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

    connection.commit()
    connection.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
