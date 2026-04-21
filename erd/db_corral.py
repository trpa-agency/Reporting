"""Read-only SQLAlchemy engine for the Corral SQL Server database.

Windows Authentication; no INSERT/UPDATE/DELETE paths are exposed.
"""
from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")


def _build_url() -> str:
    server = os.environ.get("CORRAL_SERVER", "sql24")
    database = os.environ.get("CORRAL_DATABASE", "Corral")
    odbc = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"Trusted_Connection=yes;"
        f"ApplicationIntent=ReadOnly;"
    )
    return "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc)


def get_engine() -> Engine:
    return create_engine(
        _build_url(),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    ).execution_options(readonly=True)


def reflect_metadata(engine: Engine | None = None) -> MetaData:
    engine = engine or get_engine()
    md = MetaData()
    md.reflect(bind=engine, views=True)
    return md
