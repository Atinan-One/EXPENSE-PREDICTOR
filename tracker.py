"""Core logic: cleaning (Pandas), simulation (NumPy), category + forecast models (scikit-learn).

Used by the Flask app (app.py). Nothing in here knows about the web.
"""
import os
import threading
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

BASE = Path(__file__).resolve().parent
DATA_PATH = Path(os.environ.get("EXPENSE_DATA", BASE / "data" / "expenses.csv"))
COLUMNS = ["date", "description", "amount", "category", "auto_categorised"]
DISCRETIONARY = ["Shopping", "Entertainment", "Food"]   # easiest places to save money
SUGGESTED_CATEGORIES = ["Food", "Transport", "Bills", "Shopping", "Health", "Entertainment", "Other"]
MAX_ROWS = 50_000

SAMPLE_ITEMS = {  # category -> (descriptions, typical amount in PKR)
    "Food": (["Foodpanda dinner", "KFC lunch", "Grocery store", "Tea and snacks", "Restaurant dinner", "Bakery"], 1100),
    "Transport": (["Uber ride", "Petrol", "Careem trip", "Bus fare", "Rickshaw", "Car service"], 800),
    "Shopping": (["Clothes outlet", "Daraz order", "New shoes", "Mobile accessory", "Gift for friend"], 3200),
    "Health": (["Pharmacy", "Doctor visit", "Lab test", "Gym fee"], 1800),
    "Entertainment": (["Netflix", "Cinema ticket", "Game purchase", "Spotify", "Picnic"], 1500),
}
MONTHLY_BILLS = {"Electricity bill": 9000, "Internet bill": 3500, "Mobile package": 1200, "Gas bill": 2500}


# ------------------------------------------------------------ sample data (NumPy)
def make_sample(seed=3):
    """A year of simulated expenses; 15% have no category (the model fills them in)."""
    rng = np.random.default_rng(seed)
    rows = []
    for day in pd.date_range("2025-10-01", "2026-09-30"):
        months_in = (day.year - 2025) * 12 + day.month - 10
        for _ in range(rng.poisson(1.3)):
            cat = rng.choice(list(SAMPLE_ITEMS), p=[0.40, 0.25, 0.12, 0.10, 0.13])
            names, typical = SAMPLE_ITEMS[cat]
            growth = 1 + 0.025 * months_in if cat == "Food" else 1   # food creeps up over time
            desc = rng.choice(names)
            desc = f"{desc} {rng.choice(['', '', 'paid', 'cash', 'card', 'online', 'today'])}".strip()
            if rng.random() < 0.15:                                  # messy notes, like real life
                desc = rng.choice(["misc", "payment", "other", "shopping trip", "bill", desc.split()[0].lower()])
            rows.append((day, desc, round(rng.lognormal(np.log(typical * growth), 0.5), -1), cat))
        if day.day == 5:
            for name, amount in MONTHLY_BILLS.items():
                rows.append((day, name, round(amount * rng.uniform(0.9, 1.15), -1), "Bills"))
    df = pd.DataFrame(rows, columns=["date", "description", "amount", "category"])
    df.loc[rng.random(len(df)) < 0.15, "category"] = np.nan
    return df


# ------------------------------------------------------------------ cleaning (Pandas)
def clean(raw, dedupe=True):
    """Validate and clean a raw expenses frame. Returns (frame, info). Raises ValueError."""
    missing = [c for c in ("date", "description", "amount") if c not in raw.columns]
    if missing:
        raise ValueError(f"Your file is missing column(s): {', '.join(missing)}. "
                         "Needed: date, description, amount (category is optional).")
    if len(raw) > MAX_ROWS:
        raise ValueError(f"Too many rows (max {MAX_ROWS:,}).")
    df = raw.copy()
    n0 = len(df)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["description"] = df["description"].astype(str).str.strip()
    if "category" not in df:
        df["category"] = pd.NA
    df["category"] = df["category"].astype("string").str.strip().str.title()
    df["category"] = df["category"].replace({"": pd.NA, "Nan": pd.NA, "None": pd.NA})
    if "auto_categorised" in df:
        df["auto_categorised"] = df["auto_categorised"].astype(str).str.lower().eq("true")
    else:
        df["auto_categorised"] = False
    df = df.dropna(subset=["date", "amount"])
    df = df[(df.amount > 0) & (df.amount < 1e9)]
    if dedupe:
        df = df.drop_duplicates()
    if df.empty:
        raise ValueError("No valid expenses found. Check the date and amount columns.")
    df = df[COLUMNS].sort_values("date").reset_index(drop=True)
    return df, {"rows_read": n0, "rows_kept": len(df), "rows_dropped": n0 - len(df)}


# ----------------------------------------------------- ML 1: category from description
def train_category_model(df):
    """Learn description -> category from expenses the user labelled themselves."""
    labelled = df[df.category.notna() & ~df.auto_categorised]
    if len(labelled) < 10 or labelled.category.nunique() < 2:
        return None, None
    model = make_pipeline(TfidfVectorizer(ngram_range=(1, 2)), LogisticRegression(max_iter=1000))
    accuracy = None
    if len(labelled) >= 30:
        Xtr, Xte, ytr, yte = train_test_split(labelled.description, labelled.category,
                                              test_size=0.2, random_state=0)
        accuracy = round(float(model.fit(Xtr, ytr).score(Xte, yte)), 3)
    model.fit(labelled.description, labelled.category.astype(str))
    return model, accuracy


def predict_category(model, text):
    if model is None or not text.strip():
        return None, None
    proba = model.predict_proba([text])[0]
    i = int(np.argmax(proba))
    return str(model.classes_[i]), round(float(proba[i]), 3)


# ------------------------------------------------- summary + ML 2: forecasting
def monthly_table(df):
    d = df.assign(month=df.date.dt.to_period("M"))
    table = d.pivot_table(index="month", columns="category", values="amount", aggfunc="sum", fill_value=0)
    return table.reindex(pd.period_range(table.index.min(), table.index.max(), freq="M"), fill_value=0)


def forecast_next(table):
    if len(table) < 2:
        return None
    t = np.arange(len(table)).reshape(-1, 1)
    return pd.Series({c: max(0.0, float(LinearRegression().fit(t, table[c].values).predict([[len(table)]])[0]))
                      for c in table.columns})


def overspending(table):
    """Categories where last month was 20%+ above the average of the 3 months before."""
    if len(table) < 4:
        return []
    last, base = table.iloc[-1], table.iloc[-4:-1].mean()
    out = [{"category": c, "change": round(float(last[c] / base[c] - 1), 3)}
           for c in table.columns if base[c] > 0 and last[c] > 1.2 * base[c]]
    return sorted(out, key=lambda x: -x["change"])


def budget_check(forecast, budget):
    if forecast is None or not budget or budget <= 0:
        return None
    total = float(forecast.sum())
    gap = total - budget
    if gap <= 0:
        return {"budget": budget, "status": "under", "gap": round(-gap),
                "message": f"Forecast is {-gap:,.0f} under your budget."}
    flex = float(forecast[[c for c in DISCRETIONARY if c in forecast]].sum())
    if flex > 0 and gap / flex <= 0.5:
        tip = f"Cut {', '.join(DISCRETIONARY)} by about {gap / flex:.0%} to get back on track."
    else:
        tip = "Cutting flexible spending alone is not realistic. Review fixed bills or raise the budget."
    return {"budget": budget, "status": "over", "gap": round(gap),
            "message": f"Forecast is {gap:,.0f} over your budget.", "tip": tip}


def build_report(df, model_accuracy, budget=None, today=None):
    """Summarise spending. A month still in progress is shown as 'so far' and kept out of
    averages, alerts and the forecast, because a half-finished month would distort them."""
    full_table = monthly_table(df)
    today_p = (pd.Timestamp(today) if today is not None else pd.Timestamp.today()).to_period("M")
    in_progress = len(full_table) >= 2 and full_table.index[-1] == today_p
    table = full_table.iloc[:-1] if in_progress else full_table
    so_far = full_table.iloc[-1] if in_progress else None

    categories = sorted(full_table.columns, key=lambda c: -float(full_table[c].sum()))
    table = table.reindex(columns=categories, fill_value=0)   # a category may first appear this month
    forecast = forecast_next(table)
    months = [str(m) for m in table.index]
    last = table.iloc[-1]
    notes = []
    if len(table) < 6:
        notes.append(f"Only {len(table)} full month(s) of data. Forecasts need about 6+ months to be reliable.")
    rows = []
    for c in categories:
        row = {"category": c, "last_month": round(float(last[c])), "forecast": None, "change": None,
               "so_far": None if so_far is None else round(float(so_far[c]))}
        if forecast is not None:
            row["forecast"] = round(float(forecast[c]))
            if last[c] > 0:
                row["change"] = round(float(forecast[c] / last[c] - 1), 3)
        rows.append(row)
    recent = df.sort_values("date", ascending=False, kind="stable").head(15)
    return {
        "has_data": True,
        "summary": {
            "transactions": int(len(df)), "months": len(table),
            "first_month": months[0], "last_month": months[-1],
            "avg_monthly": round(float(table.sum(axis=1).mean())),
            "last_month_total": round(float(last.sum())),
            "forecast_month": str(table.index[-1] + 1),
            "forecast_total": None if forecast is None else round(float(forecast.sum())),
            "auto_categorised": int(df.auto_categorised.sum()),
            "model_accuracy": model_accuracy,
        },
        "current": None if so_far is None else {
            "month": str(today_p), "total": round(float(so_far.sum())),
            "values": {c: round(float(so_far[c])) for c in categories}},
        "months": months, "categories": categories,
        "monthly": {c: [round(float(v)) for v in table[c]] for c in categories},
        "forecast": None if forecast is None else {c: round(float(forecast[c])) for c in categories},
        "category_table": rows,
        "alerts": overspending(table),
        "budget": budget_check(forecast, budget),
        "notes": notes,
        "recent": [{"date": r.date.strftime("%Y-%m-%d"), "description": r.description,
                    "amount": float(r.amount), "category": r.category, "auto": bool(r.auto_categorised)}
                   for r in recent.itertuples()],
    }


# ---------------------------------------------------------------------- the store
class Store:
    """Holds the user's expenses in memory and keeps a CSV copy on disk."""

    def __init__(self, path=DATA_PATH):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.df, self.model, self.accuracy = None, None, None
        if self.path.exists():
            try:
                self._set(clean(pd.read_csv(self.path), dedupe=False)[0], save=False)
            except Exception:
                self.df = None   # unreadable file: start empty rather than crash

    def _set(self, df, save=True):
        model, acc = train_category_model(df)
        unknown = df.category.isna()
        df = df.copy()
        if unknown.any():
            if model is not None:
                df.loc[unknown, "category"] = model.predict(df.loc[unknown, "description"])
                df.loc[unknown, "auto_categorised"] = True
            else:
                df.loc[unknown, "category"] = "Other"
        with self.lock:
            self.df, self.model, self.accuracy = df, model, acc
            if save:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(self.path, index=False)

    def load(self, raw):
        df, info = clean(raw)
        self._set(df)
        return info

    def add(self, date, description, amount, category=None):
        row = pd.DataFrame([{"date": date, "description": description, "amount": amount,
                             "category": category, "auto_categorised": False}])
        df, _ = clean(row)
        with self.lock:
            combined = pd.concat([self.df, df], ignore_index=True) if self.df is not None else df
        self._set(combined)
        added = self.df.iloc[-1]   # new rows are appended at the end
        return {"category": added.category, "auto": bool(added.auto_categorised)}

    def clear(self):
        with self.lock:
            self.df, self.model, self.accuracy = None, None, None
            if self.path.exists():
                self.path.unlink()

    def report(self, budget=None):
        with self.lock:
            if self.df is None or self.df.empty:
                return {"has_data": False}
            return build_report(self.df, self.accuracy, budget)
