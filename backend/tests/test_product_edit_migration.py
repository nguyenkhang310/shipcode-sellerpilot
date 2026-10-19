import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_upgrade_preserves_existing_history_and_adds_nullable_edit_reference(tmp_path,monkeypatch):
    database=tmp_path/'migration.db'
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+str(database))
    config=Config(str(Path(__file__).parents[1]/'alembic.ini'))
    command.upgrade(config,'20261017_10')
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO conversation_state (shop_slug,conversation_id) VALUES ('synthetic','retained')")
    command.upgrade(config,'head')
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT conversation_id FROM conversation_state').fetchone()[0]=='retained'
        assert 'product_edit_proposal_id' in {row[1] for row in connection.execute('PRAGMA table_info(agent_run)')}
        assert connection.execute('SELECT COUNT(*) FROM product_edit_proposal').fetchone()[0]==0
    command.downgrade(config,'20261017_10')
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT conversation_id FROM conversation_state').fetchone()[0]=='retained'
