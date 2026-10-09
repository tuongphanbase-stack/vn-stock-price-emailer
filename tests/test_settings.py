"""Run: python -m unittest discover tests

Offline checks that run on every push (see .github/workflows/tests.yml).
"""
import importlib.util
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "vn_stock_price_emailer.py")
sys.path.insert(0, ROOT)


def setting_names():
    """Every environment variable the script reads."""
    with open(SCRIPT, encoding="utf-8") as f:
        src = f.read()
    return set(re.findall(r'environ(?:\.get)?[(\[]\s*"([A-Z0-9_]+)"', src)) | set(
        re.findall(r'_env\(\s*"([A-Z0-9_]+)"', src))


def load(env=None, unset=()):
    """Import the script as a fresh module, from a scratch working directory."""
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, env or {}):
        for name in unset:
            os.environ.pop(name, None)
        os.chdir(tmp)
        try:
            spec = importlib.util.spec_from_file_location("emailer_under_test", SCRIPT)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            os.chdir(cwd)


class Settings(unittest.TestCase):
    def test_loads_with_every_setting_empty(self):
        # The workflow passes an unset repository variable as an empty string;
        # float("") once crashed currency-rate-emailer on every run.
        names = setting_names()
        self.assertTrue(names)
        load({n: "" for n in names})

    def test_loads_with_no_settings(self):
        load(unset=setting_names())


class History(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.m.HISTORY_FILE = os.path.join(self.tmp.name, "price_history.csv")

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        with open(self.m.HISTORY_FILE, encoding="utf-8") as f:
            return [line.strip().split(",") for line in f][1:]

    def write(self, rows):
        with open(self.m.HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write("timestamp,ticker,close\n" + "".join(",".join(r) + "\n" for r in rows))

    def test_only_changed_closes_are_logged(self):
        self.m.append_history({"VIC": {"close": 100.0}, "FPT": {"close": 50.0}})
        self.m.append_history({"VIC": {"close": 100.0}, "FPT": {"close": 51.0}})
        self.assertEqual([(r[1], r[2]) for r in self.rows()], [("VIC", "100.0"), ("FPT", "50.0"), ("FPT", "51.0")])

    def test_old_rows_are_dropped_but_each_ticker_keeps_its_latest(self):
        self.write([["2000-01-01 10:00", "OLD", "5.0"], ["2000-01-01 10:00", "VIC", "90.0"]])
        self.m.append_history({"VIC": {"close": 100.0}})
        self.assertEqual([(r[1], r[2]) for r in self.rows()], [("OLD", "5.0"), ("VIC", "100.0")])


if __name__ == "__main__":
    unittest.main()
