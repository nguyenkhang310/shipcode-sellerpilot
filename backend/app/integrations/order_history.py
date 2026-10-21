"""Install the shared journal without executescript's implicit COMMIT."""
from pathlib import Path
import sqlite3


def install_order_history(connection):
    columns = {row[1] for row in connection.execute('PRAGMA table_info("order")')}
    shops = {row[1] for row in connection.execute('PRAGMA table_info(shop)')}
    if not {'id', 'shop_id', 'status'} <= columns or not {'id', 'slug'} <= shops:
        return False  # Legacy single-shop schemas still use app events.
    statement = ''
    for line in Path(__file__).with_suffix('.sql').read_text(encoding='utf-8').splitlines(True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ''
    if statement.strip():
        raise ValueError('Incomplete order history schema')
    return True
