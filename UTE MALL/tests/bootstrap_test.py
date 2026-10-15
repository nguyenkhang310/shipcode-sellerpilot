"""Configuration safety of the team onboarding command; no shop writes."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from bootstrap_demo import ensure_local_configuration


class BootstrapConfigurationTests(unittest.TestCase):
    def test_new_machine_gets_private_random_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            ensure_local_configuration(root)
            value = dotenv_values(root / '.env')['SECRET_KEY']
            self.assertGreaterEqual(len(value), 32)
            self.assertEqual(os.environ['SECRET_KEY'], value)
            self.assertEqual(dotenv_values(root / '.env')['LIMITER_STORAGE_URI'], 'memory://')
            self.assertEqual(os.environ['LIMITER_STORAGE_URI'], 'memory://')
            if os.name != 'nt':
                self.assertEqual((root / '.env').stat().st_mode & 0o777, 0o600)

    def test_copying_example_with_blank_key_is_supported(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / '.env').write_text('SECRET_KEY=\nSHOP_NAME=My shop\n')
            ensure_local_configuration(root)
            values = dotenv_values(root / '.env')
            self.assertGreaterEqual(len(values['SECRET_KEY']), 32)
            self.assertEqual(values['SHOP_NAME'], 'My shop')
            self.assertEqual(values['LIMITER_STORAGE_URI'], 'memory://')

    def test_existing_secret_is_not_rotated(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / '.env').write_text('SECRET_KEY=' + 'existing-test-key-' * 3 + '\nLIMITER_STORAGE_URI=memory://\n')
            before = (root / '.env').read_bytes()
            ensure_local_configuration(root)
            ensure_local_configuration(root)
            self.assertEqual((root / '.env').read_bytes(), before)

    def test_shell_secret_takes_precedence_without_rewriting_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'SECRET_KEY': 'shell-test-key-' * 4}, clear=True):
            root = Path(directory)
            (root / '.env').write_text('SECRET_KEY=' + 'file-test-key-' * 4 + '\nLIMITER_STORAGE_URI=memory://\n')
            before = (root / '.env').read_bytes()
            ensure_local_configuration(root)
            self.assertEqual(os.environ['SECRET_KEY'], 'shell-test-key-' * 4)
            self.assertEqual((root / '.env').read_bytes(), before)

    def test_existing_redis_configuration_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / '.env').write_text('SECRET_KEY=' + 'file-test-key-' * 4 + '\nREDIS_URL=redis://localhost:6379/0\n')
            before = (root / '.env').read_bytes()
            ensure_local_configuration(root)
            self.assertEqual((root / '.env').read_bytes(), before)
            self.assertNotIn('LIMITER_STORAGE_URI', os.environ)

    def test_shell_redis_configuration_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'REDIS_URL': 'redis://localhost:6379/1'}, clear=True):
            root = Path(directory)
            ensure_local_configuration(root)
            self.assertNotIn('LIMITER_STORAGE_URI', dotenv_values(root / '.env'))
            self.assertNotIn('LIMITER_STORAGE_URI', os.environ)


if __name__ == '__main__':
    unittest.main(verbosity=2)
