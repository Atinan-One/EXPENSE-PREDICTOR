# EXPENSE-PREDICTOR
# 💰 Expense Predictor

## 📌 About the Project
Expense Predictor is a Machine Learning-based project developed using Python. It analyzes previous expense data and predicts future spending patterns. The main goal is to help users understand their spending habits, estimate upcoming expenses, and make better financial decisions.

## 🚀 Features
- Analyze historical expense data.
- Predict future expenses using Machine Learning.
- Identify spending patterns and trends.
- Help users manage their budgets.
- Data processing and analysis using Python libraries.

## 🛠️ Technologies Used
- Python
- Pandas
- NumPy
- Scikit-learn
- Matplotlib (if used)

## 🎯 Project Objective
To develop a smart expense prediction system that uses historical financial data to estimate future expenses and support better budget planning.

## 👨‍💻 Developer
Atinan Sohail

**Field:** BS Software Engineering

# Expense Tracker: ML + Web App

A web app for tracking your daily expenses. It cleans your data, guesses
categories from descriptions, shows where your money goes, forecasts next
month's spending and checks it against your budget. Your data is saved on your
own computer, so you can use it every day.

**Stack:** Python · NumPy · Pandas · scikit-learn · Flask · HTML/CSS/JavaScript

## Features
- **Upload a CSV** of your expenses, or try a year of **sample data**.
- **Add expenses** one by one. The category is suggested from the description (e.g. "Careem trip" becomes Transport).
- **Dashboard:** average per month, last full month, spending so far this month, forecast, and a stacked chart by category.
- **Budget check:** set a monthly budget and see whether the forecast is over or under, with a tip on what to cut.
- **Heads-up alerts** when a category jumps 20%+ above its recent average.
- **Download** your categorised expenses as CSV.
- **Saved automatically** in `data/expenses.csv`.
- 14 automated tests.

## Run it
```bash
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open **http://127.0.0.1:5000** and press **Try sample data**, or upload your own CSV.

Tests: `python -m unittest discover tests -v`

## Your CSV format
```
date,description,amount,category
2026-09-02,Uber ride,650,Transport
2026-09-03,Grocery store,3000,
```
`category` is optional and can be blank for some rows. Bad rows (invalid dates, zero or negative amounts, duplicates) are skipped and you are told how many.

## Project structure
```
expense-web/
├── app.py            # Flask server + JSON API
├── tracker.py        # all the logic: cleaning, ML models, report, storage
├── templates/index.html
├── static/css/style.css
├── static/js/app.js  # dashboard, SVG chart (no chart library), forms
├── tests/test_app.py
├── data/             # your saved expenses (created automatically)
└── requirements.txt
```

## API
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/report?budget=80000` | Full dashboard data |
| POST | `/api/sample` | Load sample data |
| POST | `/api/upload` | Upload a CSV |
| POST | `/api/expenses` | Add one expense |
| POST | `/api/predict-category` | Suggest a category from a description |
| GET | `/api/export` | Download CSV |
| POST | `/api/clear` | Delete all data |

## How it works
1. **Pandas** cleans the data and builds the monthly table.
2. **Machine learning #1:** TF-IDF + logistic regression learns from expenses you categorised yourself and fills in the rest (about 95% accurate on the sample data).
3. **Machine learning #2:** a linear regression per category forecasts the next month.
4. **NumPy** simulates the sample data.
5. **Flask** serves the API; JavaScript draws the dashboard.

## Design decisions
- A month that is still in progress is shown as **"so far"** and kept out of averages, alerts and the forecast. Otherwise a half-finished month would wrongly look like a huge drop in spending.
- Categories are only learned from expenses *you* labelled, never from the model's own guesses, so errors cannot reinforce themselves.
- Page text is inserted with `textContent` (never raw HTML), uploads are limited to 2 MB, and all input is validated on the server.

## Limitations and next steps
- Sample data is simulated. Accuracy on your data will differ.
- The forecast is a simple trend line and needs about 6+ months of data.
- Single user, stored in a CSV file. Next: login, a database, and income tracking.
