"""Delta read/write helpers plus a DuckDB SQL helper.

Transforms run as DuckDB SQL over Delta tables loaded via Arrow, which keeps the
bronze->silver->gold logic declarative and close to how it would look in Spark SQL.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake


def write_delta(df: pd.DataFrame, path, mode: str = "overwrite") -> None:
    kwargs = {"schema_mode": "overwrite"} if mode == "overwrite" else {}
    table = pa.Table.from_pandas(df, preserve_index=False)  # no pandas index column
    write_deltalake(str(path), table, mode=mode, **kwargs)


def upsert_delta(df: pd.DataFrame, path, key: str) -> None:
    """Insert new rows, update existing ones matched on `key` (Delta MERGE)."""
    if not (path / "_delta_log").is_dir():
        write_delta(df, path, mode="overwrite")
        return
    (
        DeltaTable(str(path))
        .merge(
            pa.Table.from_pandas(df, preserve_index=False),
            predicate=f"t.{key} = s.{key}",
            source_alias="s",
            target_alias="t",
        )
        .when_matched_update_all()
        .when_not_matched_insert_all()
        .execute()
    )


def read_delta(path, version: int | None = None) -> pd.DataFrame:
    return DeltaTable(str(path), version=version).to_pandas()


def table_version(path) -> int:
    return DeltaTable(str(path)).version()


def sql(query: str, **tables) -> pd.DataFrame:
    """Run a DuckDB query with name=delta_path tables registered."""
    con = duckdb.connect()
    try:
        for name, path in tables.items():
            con.register(name, DeltaTable(str(path)).to_pyarrow_table())
        return con.sql(query).df()
    finally:
        con.close()
