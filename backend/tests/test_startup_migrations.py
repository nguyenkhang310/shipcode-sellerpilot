import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.scripts.migrate import MigrationError, migrate


def configuration():
    return Config(str(Path(__file__).parents[1] / 'alembic.ini'))


def test_fresh_database_and_repeated_upgrade(tmp_path):
    database = tmp_path / 'agent.db'
    url = 'sqlite:///' + str(database)
    assert migrate(url, check_only=True)['pending']
    assert not database.exists(), 'Read-only doctor must not create a database'
    migrate(url)
    assert not migrate(url, check_only=True)['pending']
    migrate(url)
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '20261021_12'
        assert connection.execute('SELECT COUNT(*) FROM seller_session').fetchone()[0] == 0


def test_upgrade_existing_history_without_deleting_data(tmp_path):
    url = 'sqlite:///' + str(tmp_path / 'old.db')
    config = configuration()
    config.attributes['database_url'] = url
    command.upgrade(config, '20261019_11')
    with sqlite3.connect(tmp_path / 'old.db') as connection:
        connection.execute("INSERT INTO conversation_state (shop_slug,conversation_id) VALUES ('fixture','keep-this')")
    migrate(url)
    with sqlite3.connect(tmp_path / 'old.db') as connection:
        assert connection.execute('SELECT conversation_id FROM conversation_state').fetchone()[0] == 'keep-this'


def test_missing_revision_in_checkout_is_actionable_and_does_not_stamp_database(tmp_path):
    database = tmp_path / 'existing.db'
    url = 'sqlite:///' + str(database)
    migrate(url)
    before = database.read_bytes()
    history = tmp_path / 'alembic'
    shutil.copytree(Path(__file__).parents[1] / 'alembic', history)
    (history / 'versions/20261021_12_seller_auth.py').unlink()
    config = configuration()
    config.set_main_option('script_location', str(history))
    with pytest.raises(MigrationError, match='20261021_12'):
        migrate(url, config=config)
    assert database.read_bytes() == before


def test_unknown_database_revision_is_not_reset(tmp_path):
    database = tmp_path / 'future.db'
    url = 'sqlite:///' + str(database)
    migrate(url)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE alembic_version SET version_num='unknown_revision'")
    before = database.read_bytes()
    with pytest.raises(MigrationError, match='unknown_revision'):
        migrate(url)
    assert database.read_bytes() == before


def test_false_stamp_is_detected_without_recreating_auth_tables(tmp_path):
    database = tmp_path / 'bad-stamp.db'
    url = 'sqlite:///' + str(database)
    migrate(url)
    with sqlite3.connect(database) as connection:
        connection.execute('DROP TABLE seller_session')
    before = database.read_bytes()
    with pytest.raises(MigrationError, match='thiếu bảng xác thực'):
        migrate(url)
    assert database.read_bytes() == before
