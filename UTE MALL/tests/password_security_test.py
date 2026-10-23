"""Only synthetic passwords/hashes; does not import the shop or open databases."""
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from password_security import check_password_hash


class PasswordSecurityTests(unittest.TestCase):
    def test_pbkdf2_works_on_python_without_scrypt(self):
        password = 'Synthetic-shared-password!'
        digest = generate_password_hash(password, method='pbkdf2:sha256:600000')
        with patch.object(hashlib, 'scrypt', None, create=True):
            self.assertTrue(check_password_hash(digest, password))
            self.assertFalse(check_password_hash(digest, 'wrong'))

    def test_existing_scrypt_hash_works_when_supported(self):
        if not callable(getattr(hashlib, 'scrypt', None)):
            self.skipTest('This Python has no scrypt; unsupported-path tests still run.')
        password = 'Synthetic-scrypt-password!'
        digest = generate_password_hash(password, method='scrypt:32768:8:1')
        self.assertTrue(check_password_hash(digest, password))
        self.assertFalse(check_password_hash(digest, 'wrong'))

    def test_unsupported_or_corrupt_hash_never_accepts_a_password(self):
        for error in [AttributeError('scrypt unavailable'), ValueError('bad hash'), TypeError('invalid digest')]:
            with self.subTest(error=type(error).__name__), patch('password_security.werkzeug_check_password_hash', side_effect=error):
                with self.assertLogs('password_security', level='WARNING') as logs:
                    self.assertFalse(check_password_hash('private-hash', 'private-password'))
                self.assertNotIn('private-hash', str(logs.output))
                self.assertNotIn('private-password', str(logs.output))


if __name__ == '__main__':
    unittest.main(verbosity=2)
