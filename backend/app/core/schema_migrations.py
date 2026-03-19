from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


_VALID_REQUIREMENT_SOURCE_TYPES = ("prd", "flowchart", "api_doc")
_DEFAULT_REQUIREMENT_SOURCE_TYPE = "prd"


def _ensure_additive_columns(engine: Engine, table_name: str, column_definitions: dict) -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        if table_name not in inspector.get_table_names():
            return

        columns = {item["name"] for item in inspector.get_columns(table_name)}
        for column_name, ddl in column_definitions.items():
            if column_name in columns:
                continue
            conn.execute(text("ALTER TABLE {0} ADD COLUMN {1}".format(table_name, ddl)))


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


def ensure_requirement_source_type_values(engine: Engine) -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        if "requirements" not in inspector.get_table_names():
            return

        columns = {item["name"] for item in inspector.get_columns("requirements")}
        if "source_type" not in columns:
            return

        valid_values_sql = ", ".join(f"'{value}'" for value in _VALID_REQUIREMENT_SOURCE_TYPES)
        conn.execute(
            text(
                "UPDATE requirements "
                "SET source_type = :default_source_type "
                f"WHERE source_type NOT IN ({valid_values_sql})"
            ),
            {"default_source_type": _DEFAULT_REQUIREMENT_SOURCE_TYPE},
        )


def ensure_test_cases_precondition_column(engine: Engine) -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)
        if "test_cases" not in inspector.get_table_names():
            return

        columns = {item["name"] for item in inspector.get_columns("test_cases")}
        if "precondition" not in columns:
            conn.execute(text("ALTER TABLE test_cases ADD COLUMN precondition TEXT DEFAULT ''"))


def ensure_rule_tree_session_async_columns(engine: Engine) -> None:
    _ensure_additive_columns(
        engine,
        "rule_tree_sessions",
        {
            "progress_stage": "progress_stage VARCHAR(50)",
            "progress_message": "progress_message TEXT",
            "progress_percent": "progress_percent INTEGER",
            "last_error": "last_error TEXT",
            "generated_tree_snapshot": "generated_tree_snapshot TEXT",
            "reviewed_tree_snapshot": "reviewed_tree_snapshot TEXT",
            "current_task_started_at": "current_task_started_at DATETIME",
            "current_task_finished_at": "current_task_finished_at DATETIME",
        },
    )


def ensure_risk_analysis_task_columns(engine: Engine) -> None:
    _ensure_additive_columns(
        engine,
        "risk_analysis_tasks",
        {
            "progress_message": "progress_message TEXT",
            "progress_percent": "progress_percent INTEGER",
            "last_error": "last_error TEXT",
            "snapshot_id": "snapshot_id INTEGER",
            "result_json": "result_json TEXT",
            "current_task_started_at": "current_task_started_at DATETIME",
            "current_task_finished_at": "current_task_finished_at DATETIME",
            "created_at": "created_at DATETIME",
            "updated_at": "updated_at DATETIME",
        },
    )


def ensure_product_doc_chunk_hierarchy_columns(engine: Engine) -> None:
    _ensure_additive_columns(
        engine,
        "product_doc_chunks",
        {
            "parent_title": "parent_title VARCHAR(255)",
            "heading_level": "heading_level INTEGER",
        },
    )


def ensure_risk_convergence_columns(engine: Engine) -> None:
    _ensure_additive_columns(
        engine,
        "risk_items",
        {
            "analysis_stage": "analysis_stage VARCHAR(20)",
            "validity": "validity VARCHAR(20) DEFAULT 'active'",
            "origin_snapshot_id": "origin_snapshot_id INTEGER",
            "last_seen_snapshot_id": "last_seen_snapshot_id INTEGER",
            "last_analysis_at": "last_analysis_at DATETIME",
            "converted_node_id": "converted_node_id VARCHAR(64)",
        },
    )
    _ensure_additive_columns(
        engine,
        "evidence_blocks",
        {
            "chunk_content_hash": "chunk_content_hash VARCHAR(64)",
        },
    )
    _ensure_additive_columns(
        engine,
        "effective_requirement_snapshots",
        {
            "basis_hash": "basis_hash VARCHAR(64)",
        },
    )


def ensure_product_knowledge_columns(engine: Engine) -> None:
    _ensure_additive_columns(
        engine,
        "projects",
        {
            "product_code": "product_code VARCHAR(64)",
        },
    )
    _ensure_additive_columns(
        engine,
        "risk_items",
        {
            "risk_source": "risk_source VARCHAR(20) DEFAULT 'rule_tree'",
            "clarification_text": "clarification_text TEXT",
            "doc_update_needed": "doc_update_needed BOOLEAN DEFAULT 0",
        },
    )
    _ensure_additive_columns(
        engine,
        "product_doc_chunks",
        {
            "parent_title": "parent_title VARCHAR(255)",
            "heading_level": "heading_level INTEGER",
        },
    )
