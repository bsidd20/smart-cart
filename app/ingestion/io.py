"""Delta read/write helpers, table maintenance, and a DuckDB SQL helper.

Transforms run as DuckDB SQL over Delta tables loaded via Arrow, which keeps the
bronze->silver->gold logic declarative and close to how it would look in Spark SQL.

Tables can be partitioned on write; maintenance helpers compact small files and
Z-order data for better file skipping (see scripts/benchmark.py for the effect).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake


def write_delta(
    df: pd.DataFrame, path, mode: str = "overwrite", partition_by: list[str] | None = None
) -> None:
    kwargs = {"schema_mode": "overwrite"} if mode == "overwrite" else {}
    if partition_by:
        kwargs["partition_by"] = partition_by
    table = pa.Table.from_pandas(df, preserve_index=False)  # no pandas index column
    write_deltalake(str(path), table, mode=mode, **kwargs)


def upsert_delta(df: pd.DataFrame, path, key: str, partition_by: list[str] | None = None) -> None:
    """Insert new rows, update existing ones matched on `key` (Delta MERGE)."""
    if not (path / "_delta_log").is_dir():
        write_delta(df, path, mode="overwrite", partition_by=partition_by)
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


def file_count(path) -> int:
    """Number of data files backing the table (small-file pressure indicator)."""
    return len(DeltaTable(str(path)).file_uris())


def compact(path) -> dict:
    """Merge small files into larger ones. Returns optimize metrics."""
    return DeltaTable(str(path)).optimize.compact()


def zorder(path, columns: list[str]) -> dict:
    """Co-locate rows by the given columns so queries skip more files."""
    return DeltaTable(str(path)).optimize.z_order(columns)


def sql(query: str, **tables) -> pd.DataFrame:
    """Run a DuckDB query with the given name=delta_path tables registered."""
    con = duckdb.connect()
    try:
        for name, path in tables.items():
            con.register(name, DeltaTable(str(path)).to_pyarrow_table())
        return con.sql(query).df()
    finally:
        con.close()
