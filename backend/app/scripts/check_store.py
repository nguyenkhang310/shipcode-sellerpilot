"""Fail fast when the app and local Seller Centre point at different ledgers."""
import os
from pathlib import Path
from dotenv import dotenv_values
from app.core.config import Settings, BACKEND_DIR, REPO_DIR


def same_shop_database(api_path, store_value, *, backend_dir=BACKEND_DIR, store_dir=REPO_DIR / 'UTE MALL'):
    api = Path(api_path).expanduser()
    web = Path(store_value).expanduser() if store_value else store_dir / 'instance/ecommerce.db'
    api = (api if api.is_absolute() else backend_dir / api).resolve()
    web = (web if web.is_absolute() else store_dir / web).resolve()
    return api == web or api.is_file() and web.is_file() and os.path.samefile(api, web)


def main():
    settings = Settings()
    values = dotenv_values(REPO_DIR / 'UTE MALL/.env')
    selected = os.environ.get('STORE_DATABASE_PATH') or values.get('STORE_DATABASE_PATH')
    if not same_shop_database(settings.shop_database_path, selected):
        print('FAIL · SHOP_DATABASE_PATH của API và STORE_DATABASE_PATH của web trỏ tới hai database khác nhau. Cấu hình cùng một đường dẫn tuyệt đối trước khi chạy để tránh lệch đơn/tồn kho.')
        return 1
    print('PASS · App và Kênh Người Bán local dùng chung database.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
