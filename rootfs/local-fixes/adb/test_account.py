"""Verify daemon account selection without opening USB devices."""
from pathlib import Path
import os
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

Gadget = runpy.run_path(str(Path(__file__).with_name('tb322fc-adbd')))['Gadget']


class AccountTests(unittest.TestCase):
    def test_missing_account_fails_before_lookup(self):
        with patch.dict(os.environ, {}, clear=True), patch('pwd.getpwnam') as lookup:
            with self.assertRaisesRegex(RuntimeError, 'Set ADBD_USER'):
                Gadget()
            lookup.assert_not_called()

    def test_root_account_rejected(self):
        with patch.dict(os.environ, ADBD_USER='root'), patch('pwd.getpwnam', return_value=SimpleNamespace(pw_uid=0)):
            with self.assertRaisesRegex(RuntimeError, 'unprivileged'):
                Gadget()

    def test_configured_unprivileged_account_used(self):
        account = SimpleNamespace(pw_uid=1234)
        with patch.dict(os.environ, ADBD_USER='test-user'), patch('pwd.getpwnam', return_value=account) as lookup:
            self.assertIs(Gadget().account, account)
            lookup.assert_called_once_with('test-user')
