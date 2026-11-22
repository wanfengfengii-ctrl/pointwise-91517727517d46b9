import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from os import PathLike


def open_database(path: str | PathLike[str]) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute('PRAGMA foreign_keys = ON')
    except BaseException:
        connection.close()
        raise
    return connection


@contextmanager
def write_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise


def create_tables(connection: sqlite3.Connection, definitions: Iterable[str]) -> None:
    with write_transaction(connection):
        for definition in definitions:
            connection.execute(definition)
