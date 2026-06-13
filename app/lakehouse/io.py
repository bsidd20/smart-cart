"""Read/write helpers for Delta tables, plus a DuckDB SQL helper.

Transforms run as DuckDB SQL over Delta tables (loaded via Arrow), which keeps the
Bronze->Silver->Gold logic declarative and close to how it would look in Spark SQL.
"""
from __future__ import annotations

import duckdb
import pandas as pd
from deltalake import DeltaTable, write_deltalake


def write_delta(df: pd.DataFrame, path, mode: str = "overwrite") -> None:
    kwargs = {"schema_mode": "overwrite"} if mode == "overwrite" else {}
    write_deltalake(str(path), df, mode=mode, **kwargs)


def read_delta(path, version: int | None = None) -> pd.DataFrame:
    return DeltaTable(str(path), version=version).to_pandas()


def table_version(path) -> int:
    return DeltaTable(str(path)).version()


def sql(query: str, **tables) -> pd.DataFrame:
    """Run a DuckDB query with the given name=delta_path tables registered."""
    con = duckdb.connect()
    try:
        for name, path in tables.items():
            con.register(name, DeltaTable(str(path)).to_pyarrow_table())
        return con.sql(query).df()
    finally:
        con.close()
