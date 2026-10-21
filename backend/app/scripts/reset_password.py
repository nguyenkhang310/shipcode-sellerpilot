"""Local owner recovery. No passwords in arguments, environment or logs."""
import getpass
import secrets
import sqlite3
import sys

from werkzeug.security import generate_password_hash
from app.core.config import Settings
from app.integrations.ute_mall import UTEMallRepository, ShopDatabaseError
from app.services.auth import seller_user


def reset_password(shop, username, password, confirmation):
    if len(password) < 12 or len(password) > 256:
        raise ValueError('Mật khẩu phải có từ 12 đến 256 ký tự.')
    if not secrets.compare_digest(password.encode(), confirmation.encode()):
        raise ValueError('Hai lần nhập mật khẩu không khớp. Chưa thay đổi tài khoản.')
    user = seller_user(shop, login_id=username.strip())
    if not user or not user['membership'] or user['membership']['role'] != 'owner':
        raise ValueError('Không tìm thấy tài khoản chủ shop đang liên kết. Chưa thay đổi dữ liệu.')
    digest = generate_password_hash(password)
    with shop._connect() as connection:
        result = connection.execute('UPDATE user SET password_hash=? WHERE id=? AND password_hash=?',
                                    (digest, user['id'], user['password_hash']))
        if result.rowcount != 1:
            raise ValueError('Tài khoản vừa thay đổi. Vui lòng chạy lại lệnh.')
        connection.commit()
    return user['username']


def main():
    if not sys.stdin.isatty():
        print('Hãy chạy lệnh trực tiếp trong terminal để nhập mật khẩu an toàn.', file=sys.stderr)
        return 1
    settings = Settings()
    shop = UTEMallRepository(settings.shop_database_path, settings.shop_timezone, settings.seller_shop_slug)
    print('Đặt lại mật khẩu chủ shop local. Sản phẩm và đơn hàng được giữ nguyên.')
    try:
        username = input('Tên đăng nhập [utech]: ').strip() or 'utech'
        password = getpass.getpass('Mật khẩu mới (ít nhất 12 ký tự, không hiện khi gõ): ')
        confirmation = getpass.getpass('Nhập lại mật khẩu mới: ')
        username = reset_password(shop, username, password, confirmation)
    except (ValueError, ShopDatabaseError, sqlite3.Error) as error:
        # Never print SQL exceptions: bound parameters may contain credentials.
        print(str(error) if isinstance(error, ValueError) else 'Không truy cập được database shop. Kiểm tra cấu hình và thử lại.', file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print('\nĐã hủy. Chưa đổi mật khẩu.')
        return 1
    print(f'Đã đổi mật khẩu cho {username}. Dùng mật khẩu mới để đăng nhập app và Kênh Người Bán local. Phiên app cũ sẽ hết hiệu lực.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
