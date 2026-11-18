"""Validate the checked-out migration history before upgrading existing data."""
import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from app.core.config import BACKEND_DIR, Settings
from app.db.session import build_engine


class MigrationError(RuntimeError):
    pass


def migrate(database_url: str, *, check_only=False, config: Config | None = None):
    config = config or Config(str(BACKEND_DIR / 'alembic.ini'))
    config.attributes['database_url'] = database_url
    try:
        scripts = ScriptDirectory.from_config(config)
        heads = scripts.get_heads()
        list(scripts.walk_revisions())
        if len(heads) != 1 or scripts.get_revision('20261021_12') is None:
            raise MigrationError('Thiếu migration xác thực người bán 20261021_12.')
    except Exception as error:
        raise MigrationError(
            'Bộ migration trong mã nguồn chưa đầy đủ (cần revision 20261021_12). '
            'Kiểm tra git branch --show-current, cập nhật toàn bộ nhánh main bằng git pull --ff-only origin main. '
            'Không xóa database hoặc chạy alembic stamp head để bỏ qua lỗi.'
        ) from error

    url = make_url(database_url)
    database = Path(url.database) if url.database and url.database != ':memory:' else None
    if database and not database.is_absolute():
        database = BACKEND_DIR / database
    existing = url.get_backend_name() != 'sqlite' or database is not None and database.exists()
    current = ()
    if existing:
        engine = build_engine(database_url)
        try:
            with engine.connect() as connection:
                current = MigrationContext.configure(connection).get_current_heads()
                for revision in current:
                    try:
                        if scripts.get_revision(revision) is None:
                            raise ValueError('Unknown revision')
                    except Exception as error:
                        raise MigrationError(
                            f'Database đang ở revision {revision}, nhưng nhánh hiện tại không có migration đó. '
                            'Cập nhật đúng nhánh main và giữ nguyên database; không tự stamp hoặc hạ revision.'
                        ) from error
                if set(current) == set(heads):
                    missing = {'seller_session', 'seller_login_attempt'} - set(inspect(connection).get_table_names())
                    if missing:
                        raise MigrationError('Database đã gắn revision mới nhưng thiếu bảng xác thực. '
                                             'Cần kiểm tra bản sao lưu; không tự ghi đè hoặc stamp lại.')
        finally:
            engine.dispose()
    if not check_only:
        command.upgrade(config, 'head')
    return {'current': current, 'head': heads[0], 'pending': set(current) != set(heads)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate without migrating or changing data')
    args = parser.parse_args()
    try:
        result = migrate(Settings().database_url, check_only=args.check)
    except MigrationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(f'Không kiểm tra/cập nhật được database ({type(error).__name__}). '
              'Kiểm tra cấu hình DATABASE_URL và quyền truy cập; dữ liệu không được tự đặt lại.', file=sys.stderr)
        return 1
    print(f'Migration hợp lệ · head={result["head"]}' + (' · Có bản cập nhật cần chạy.' if args.check and result['pending'] else ''))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
