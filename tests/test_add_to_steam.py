"""Exercise desktop paths and file URLs without modifying a Steam library."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader(
    "add_to_steam", str(ROOT / "packages/steam-bootstrap/steamos-add-to-steam"))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)


class AddToSteam(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.application = self.root / '中文 game "quoted" \'single\' $HOME $(id) `id` %20 #1.desktop'
        self.application.write_text("[Desktop Entry]\nType=Application\nName=Test\nExec=true\n")

    def mime(self, value):
        return patch.object(helper.subprocess, "run", return_value=
                            subprocess.CompletedProcess([], 0, stdout=value + "\n"))

    def test_paths_and_file_urls_round_trip_literal_characters(self):
        for value in (str(self.application), self.application.as_uri(),
                      self.application.as_uri().replace("file:///", "file://localhost/")):
            with self.subTest(value=value), self.mime("application/x-desktop") as run:
                url = helper.steam_url(value)
                self.assertEqual(unquote(url.removeprefix("steam://addnonsteamgame/")), str(self.application))
                run.assert_called_once_with(
                    ["/usr/bin/kmimetypefinder", str(self.application)],
                    check=True, capture_output=True, text=True)

    def test_remote_urls_and_directories_are_rejected_before_mime_query(self):
        for value in ("https://example.org/game.exe", "smb://server/game.exe",
                      "file://server/game.exe", self.application.as_uri() + "#fragment",
                      str(self.root), str(self.root / "missing.desktop")):
            with self.subTest(value=value), self.mime("application/x-desktop") as run:
                with self.assertRaises((ValueError, OSError)):
                    helper.steam_url(value)
                run.assert_not_called()

    def test_native_programs_need_execute_permission_but_windows_files_do_not(self):
        for mime in ("application/x-shellscript", "text/x-shellscript"):
            with self.subTest(mime=mime), self.mime(mime):
                self.application.chmod(0o644)
                with self.assertRaisesRegex(ValueError, "not executable"):
                    helper.steam_url(str(self.application))
                self.application.chmod(0o755)
                self.assertTrue(helper.steam_url(str(self.application)).startswith("steam://"))
        self.application.chmod(0o644)
        with self.mime("application/vnd.microsoft.portable-executable"):
            self.assertTrue(helper.steam_url(str(self.application)).startswith("steam://"))
        with self.mime("text/plain"):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                helper.steam_url(str(self.application))

    def test_dispatch_passes_a_single_uri_argument_to_existing_launcher(self):
        with patch.object(helper.os, "getuid", return_value=1000), \
             patch.object(helper, "prepare_steam_marker") as marker, \
             self.mime("application/x-desktop") as run:
            self.assertEqual(helper.main(["--", self.application.as_uri()]), 0)
            marker.assert_called_once_with()
            argv = run.call_args.args[0]
            self.assertEqual(argv[0], "/usr/bin/steam")
            self.assertEqual(len(argv), 2)
            self.assertEqual(unquote(argv[1].removeprefix("steam://addnonsteamgame/")), str(self.application))
            self.assertEqual(run.call_args.kwargs, {"check": True})

    def test_marker_does_not_follow_symlinks(self):
        marker = self.root / "marker"
        target = self.root / "untouched"
        target.write_text("keep")
        marker.symlink_to(target)
        original_open = os.open
        with patch.object(helper.os, "open", side_effect=lambda _, flags, mode:
                          original_open(marker, flags, mode)):
            with self.assertRaises(OSError):
                helper.prepare_steam_marker()
        self.assertEqual(target.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
