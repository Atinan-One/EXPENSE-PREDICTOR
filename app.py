"""Flask web app for the expense tracker.

Run:  python app.py   then open http://127.0.0.1:5000
"""
import io

import pandas as pd
from flask import Flask, Response, jsonify, render_template, request

import tracker as tr

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024   # 2 MB upload limit
STORE = tr.Store()


def get_budget():
    try:
        b = float(request.args.get("budget", ""))
        return b if b > 0 else None
    except ValueError:
        return None


def fail(message, code=400):
    return jsonify(error=message), code


@app.errorhandler(413)
def too_large(_):
    return fail("File too large (max 2 MB).", 413)


@app.get("/")
def index():
    return render_template("index.html", categories=tr.SUGGESTED_CATEGORIES)


@app.get("/api/report")
def report():
    return jsonify(STORE.report(get_budget()))


@app.post("/api/sample")
def sample():
    STORE.load(tr.make_sample())
    return jsonify(STORE.report(get_budget()))


@app.post("/api/upload")
def upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        return fail("Choose a CSV file to upload.")
    try:
        raw = pd.read_csv(file.stream)
    except Exception:
        return fail("Could not read that file. Please upload a valid CSV.")
    try:
        info = STORE.load(raw)
    except ValueError as e:
        return fail(str(e))
    out = STORE.report(get_budget())
    out["import_info"] = info
    return jsonify(out)


@app.post("/api/predict-category")
def predict_category():
    data = request.get_json(silent=True) or {}
    text = str(data.get("description", "")).strip()[:100]
    category, confidence = tr.predict_category(STORE.model, text)
    return jsonify(category=category, confidence=confidence)


@app.post("/api/expenses")
def add_expense():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("Send the expense as a JSON object.")
    description = str(data.get("description", "")).strip()
    if not description or len(description) > 100:
        return fail("Description is required (max 100 characters).")
    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return fail("Amount must be a number.")
    if not 0 < amount < 1e9:
        return fail("Amount must be greater than zero.")
    date = pd.to_datetime(str(data.get("date", "")), errors="coerce", format="%Y-%m-%d")
    if pd.isna(date):
        return fail("Date must look like 2026-10-17.")
    category = str(data.get("category") or "").strip()[:30] or None
    try:
        added = STORE.add(date, description, amount, category)
    except ValueError as e:
        return fail(str(e))
    out = STORE.report(get_budget())
    out["added"] = added
    return jsonify(out)


@app.get("/api/export")
def export():
    if STORE.df is None:
        return fail("There is no data to export yet.", 404)
    buf = io.StringIO()
    STORE.df.to_csv(buf, index=False)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=expenses_categorised.csv"})


@app.post("/api/clear")
def clear():
    STORE.clear()
    return jsonify(has_data=False)


if __name__ == "__main__":
    app.run(debug=True)
