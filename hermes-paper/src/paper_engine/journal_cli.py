from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from paper_engine.journal_store import JournalStore
from paper_engine.journal_types import JournalError, JournalStream

app = typer.Typer(help="SQLite append-only journal utilities")
console = Console()


@app.callback()
def main() -> None:
    pass


@app.command("inspect")
def inspect_journal(
    db: Annotated[Path, typer.Option("--db")],
    expect_schema_version: Annotated[int | None, typer.Option("--expect-schema-version")] = None,
) -> None:
    try:
        inspection = JournalStore(db).inspect()
    except JournalError as exc:
        console.print(f"journal inspect failed | {exc}")
        raise typer.Exit(1) from exc
    if expect_schema_version is not None and inspection.schema_version != expect_schema_version:
        console.print(
            " ".join(
                (
                    "journal inspect failed |",
                    f"schema_version={inspection.schema_version}",
                    f"expected={expect_schema_version}",
                )
            )
        )
        raise typer.Exit(1)
    count_text = " ".join(f"{stream.value}={inspection.stream_counts[stream]}" for stream in JournalStream)
    console.print(
        " ".join(
            (
                f"journal inspect | db={inspection.db_path}",
                f"schema_version={inspection.schema_version}",
                f"journal_mode={inspection.journal_mode}",
                f"events={inspection.event_count}",
                count_text,
            )
        )
    )
