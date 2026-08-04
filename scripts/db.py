#!/usr/bin/env python3
"""Apply and validate the plain-SQL Infra Timelapse database files."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIGRATIONS_DIR = ROOT / "db" / "migrations"


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class PsqlClient:
    def __init__(self, mode: str) -> None:
        self.mode = self._resolve_mode(mode)

    @staticmethod
    def _resolve_mode(mode: str) -> str:
        if mode != "auto":
            return mode
        if shutil.which("psql"):
            return "local"
        if shutil.which("docker"):
            return "docker"
        raise RuntimeError(
            "Neither psql nor Docker is available. Install one or set "
            "DB_EXECUTION_MODE to 'local' or 'docker'."
        )

    def _base_command(self) -> list[str]:
        if self.mode == "local":
            psql = shutil.which("psql")
            if psql is None:
                raise RuntimeError("DB execution mode is local, but psql is unavailable")
            database_url = os.getenv(
                "DATABASE_URL",
                "postgresql://infra_timelapse:infra_timelapse@localhost:5432/infra_timelapse",
            )
            return [psql, database_url, "-X", "-v", "ON_ERROR_STOP=1"]

        if self.mode == "docker":
            docker = shutil.which("docker")
            if docker is None:
                raise RuntimeError("DB execution mode is docker, but Docker is unavailable")
            database = os.getenv("POSTGRES_DB", "infra_timelapse")
            user = os.getenv("POSTGRES_USER", "infra_timelapse")
            return [
                docker,
                "compose",
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                user,
                "-d",
                database,
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
            ]

        raise RuntimeError(f"Unsupported database execution mode: {self.mode}")

    def _file_argument(self, path: Path) -> str:
        resolved = path.resolve()
        if self.mode == "docker":
            try:
                return str(resolved.relative_to(ROOT))
            except ValueError as error:
                raise RuntimeError(
                    f"Docker mode can only execute SQL files below {ROOT}"
                ) from error
        return str(resolved)

    def execute_sql(self, sql: str, *, capture: bool = False) -> str:
        command = [*self._base_command(), "-c", sql]
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=capture,
        )
        return result.stdout if capture else ""

    def query_rows(self, sql: str) -> list[str]:
        command = [*self._base_command(), "-A", "-t", "-c", sql]
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        return [line for line in result.stdout.splitlines() if line]

    def execute_file(self, path: Path) -> None:
        command = [*self._base_command(), "-f", self._file_argument(path)]
        subprocess.run(command, cwd=ROOT, check=True)

    def execute_migration(self, path: Path, filename: str, checksum: str) -> None:
        record_sql = (
            "INSERT INTO public.schema_migrations (filename, sha256) VALUES ("
            f"{sql_literal(filename)}, {sql_literal(checksum)});"
        )
        command = [
            *self._base_command(),
            "--single-transaction",
            "-f",
            self._file_argument(path),
            "-c",
            record_sql,
        ]
        subprocess.run(command, cwd=ROOT, check=True)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrate(client: PsqlClient, migrations_dir: Path) -> None:
    client.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS public.schema_migrations (
            filename text PRIMARY KEY,
            sha256 character(64) NOT NULL,
            applied_at timestamp with time zone NOT NULL DEFAULT now(),
            CONSTRAINT schema_migrations_sha256_ck
                CHECK (btrim(sha256) ~ '^[0-9a-f]{64}$')
        );
        """
    )

    applied: dict[str, str] = {}
    for row in client.query_rows(
        "SELECT filename || E'\\t' || btrim(sha256) "
        "FROM public.schema_migrations ORDER BY filename;"
    ):
        filename, checksum = row.split("\t", 1)
        applied[filename] = checksum

    migration_paths = sorted(migrations_dir.glob("*.sql"))
    if not migration_paths:
        raise RuntimeError(f"No SQL migrations found in {migrations_dir}")

    for migration_path in migration_paths:
        filename = migration_path.name
        checksum = file_sha256(migration_path)
        existing_checksum = applied.get(filename)
        if existing_checksum is not None:
            if existing_checksum != checksum:
                raise RuntimeError(
                    f"Applied migration {filename} has checksum {existing_checksum}, "
                    f"but the file now has {checksum}. Add a new migration instead "
                    "of editing an applied one."
                )
            print(f"skip  {filename}")
            continue

        print(f"apply {filename}")
        client.execute_migration(migration_path, filename, checksum)


def run_files(client: PsqlClient, paths: Sequence[Path]) -> None:
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"SQL file does not exist: {path}")
        print(f"run   {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
        client.execute_file(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("auto", "local", "docker"),
        default=os.getenv("DB_EXECUTION_MODE", "auto"),
        help="how to invoke psql (default: auto)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate_parser = subparsers.add_parser("migrate", help="apply new migrations")
    migrate_parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIR,
    )

    run_parser = subparsers.add_parser("run", help="execute one or more SQL files")
    run_parser.add_argument("paths", nargs="+", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        client = PsqlClient(args.mode)
        if args.command == "migrate":
            migrate(client, args.migrations_dir.resolve())
        elif args.command == "run":
            run_files(client, [path.resolve() for path in args.paths])
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
