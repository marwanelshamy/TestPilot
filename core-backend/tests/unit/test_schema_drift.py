"""Architecture conformance: the ORM models (used by the migration) and the agreed contract
db/schema.sql must define the same tables and columns."""

import pglast
from pglast import ast

from app.core.database import Base
from app.repositories import models  # noqa: F401
from tests.conftest import REPO_ROOT


def schema_sql_tables() -> dict[str, set[str]]:
    sql = (REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    tables: dict[str, set[str]] = {}
    for raw in pglast.parse_sql(sql):
        stmt = raw.stmt
        if isinstance(stmt, ast.CreateStmt):
            cols = {elt.colname for elt in stmt.tableElts if isinstance(elt, ast.ColumnDef)}
            tables[stmt.relation.relname] = cols
    return tables


def test_models_match_schema_sql():
    sql_tables = schema_sql_tables()
    orm_tables = {name: {c.name for c in t.columns} for name, t in Base.metadata.tables.items()}
    assert sorted(orm_tables) == sorted(sql_tables)
    for name in sql_tables:
        assert orm_tables[name] == sql_tables[name], f"column mismatch in {name}"


def test_has_the_14_agreed_tables():
    # 13 entities of the M2 Data view + processed_message
    assert len(schema_sql_tables()) == 14
