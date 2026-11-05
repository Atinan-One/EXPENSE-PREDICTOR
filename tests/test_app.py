"""Tests. Run with:  python -m unittest discover tests -v"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["EXPENSE_DATA"] = str(Path(tempfile.mkdtemp()) / "expenses.csv")   # never touch real data
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module  # noqa: E402
import tracker as tr  # noqa: E402

GOOD = {"date": "2026-10-03", "description": "Uber ride to office", "amount": 750, "category": ""}


class ExpenseAppTests(unittest.TestCase):
    def setUp(self):
        app_module.STORE = tr.Store(os.environ["EXPENSE_DATA"] + ".case")   # fresh store per test
        app_module.STORE.clear()
        self.client = app_module.app.test_client()

    def load_sample(self):
        return self.client.post("/api/sample").get_json()

    def test_home_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Expense Tracker", r.data)

    def test_empty_report(self):
        self.assertFalse(self.client.get("/api/report").get_json()["has_data"])

    def test_sample_report(self):
        r = self.load_sample()
        self.assertTrue(r["has_data"])
        self.assertEqual(r["summary"]["months"], 12)
        self.assertGreater(r["summary"]["forecast_total"], 0)
        self.assertGreater(r["summary"]["auto_categorised"], 0)
        self.assertEqual(len(r["months"]), len(next(iter(r["monthly"].values()))))

    def test_current_month_is_kept_out_of_forecast(self):
        import pandas as pd
        df, _ = tr.clean(tr.make_sample())
        extra = pd.DataFrame([{"date": pd.Timestamp("2026-10-16"), "description": "tea", "amount": 300,
                               "category": "Food", "auto_categorised": False}])
        both = pd.concat([df, extra], ignore_index=True)
        mid = tr.build_report(both, None, today="2026-10-16")        # October still in progress
        done = tr.build_report(both, None, today="2026-12-01")       # October finished
        self.assertEqual(mid["summary"]["last_month"], "2026-09")
        self.assertEqual(mid["current"]["total"], 300)
        self.assertEqual(mid["summary"]["forecast_total"], tr.build_report(df, None, today="2026-10-16")["summary"]["forecast_total"])
        self.assertIsNone(done["current"])
        self.assertEqual(done["summary"]["last_month"], "2026-10")

    def test_budget_check(self):
        self.load_sample()
        over = self.client.get("/api/report?budget=1000").get_json()["budget"]
        under = self.client.get("/api/report?budget=9999999").get_json()["budget"]
        self.assertEqual(over["status"], "over")
        self.assertEqual(under["status"], "under")
        self.assertIsNone(self.client.get("/api/report?budget=abc").get_json()["budget"])

    def test_add_expense_autocategorises(self):
        self.load_sample()
        before = self.client.get("/api/report").get_json()["summary"]["transactions"]
        r = self.client.post("/api/expenses", json=GOOD).get_json()
        self.assertEqual(r["summary"]["transactions"], before + 1)
        self.assertEqual(r["added"]["category"], "Transport")
        self.assertTrue(r["added"]["auto"])

    def test_add_expense_manual_category(self):
        self.load_sample()
        r = self.client.post("/api/expenses", json=dict(GOOD, category="food")).get_json()
        self.assertEqual(r["added"]["category"], "Food")
        self.assertFalse(r["added"]["auto"])

    def test_add_expense_validation(self):
        for bad in (dict(GOOD, amount="abc"), dict(GOOD, amount=-5), dict(GOOD, description=""),
                    dict(GOOD, date="03/10/2026"), dict(GOOD, date="")):
            r = self.client.post("/api/expenses", json=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("error", r.get_json())
        self.assertEqual(self.client.post("/api/expenses", data="hello").status_code, 400)

    def test_first_expense_without_model(self):
        r = self.client.post("/api/expenses", json=GOOD).get_json()
        self.assertTrue(r["has_data"])
        self.assertEqual(r["added"]["category"], "Other")
        self.assertIsNone(r["summary"]["forecast_total"])

    def test_upload_messy_csv(self):
        csv = (b"date,description,amount,category\n2026-06-02,Uber ride,650,Transport\n"
               b"2026-06-03, KFC lunch ,1200,food\n2026-06-03, KFC lunch ,1200,food\n"
               b"not a date,Pharmacy,500,Health\n2026-06-10,Netflix,-900,Entertainment\n"
               b"2026-07-05,Electricity bill,8800,\n")
        r = self.client.post("/api/upload", data={"file": (io.BytesIO(csv), "m.csv")},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        info = r.get_json()["import_info"]
        self.assertEqual((info["rows_read"], info["rows_kept"]), (6, 3))

    def test_upload_errors(self):
        r = self.client.post("/api/upload", data={}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        bad = b"when,what\n2026-01-01,tea\n"
        r = self.client.post("/api/upload", data={"file": (io.BytesIO(bad), "b.csv")},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        self.assertIn("missing column", r.get_json()["error"])

    def test_export_and_clear(self):
        self.assertEqual(self.client.get("/api/export").status_code, 404)
        self.load_sample()
        r = self.client.get("/api/export")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"description", r.data)
        self.client.post("/api/clear")
        self.assertFalse(self.client.get("/api/report").get_json()["has_data"])

    def test_predict_category_endpoint(self):
        self.load_sample()
        r = self.client.post("/api/predict-category", json={"description": "Careem trip"}).get_json()
        self.assertEqual(r["category"], "Transport")

    def test_data_survives_restart(self):
        self.load_sample()
        reloaded = tr.Store(app_module.STORE.path)
        self.assertEqual(len(reloaded.df), len(app_module.STORE.df))


if __name__ == "__main__":
    unittest.main()
