from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_requirements_versioning_columns(engine: Engine) -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        if "requirements" not in inspector.get_table_names():
            return

        columns = {item["name"] for item in inspector.get_columns("requirements")}
        if "version" not in columns:
            conn.execute(text("ALTER TABLE requirements ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))
        if "requirement_group_id" not in columns:
            conn.execute(text("ALTER TABLE requirements ADD COLUMN requirement_group_id INTEGER"))

        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_requirements_requirement_group_id "
                "ON requirements (requirement_group_id)"
            )
        )
