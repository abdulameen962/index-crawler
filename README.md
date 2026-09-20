# 📊 NGX Index Fund Replicator

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Scrapy](https://img.shields.io/badge/Scrapy-2.11%2B-5B8A5A.svg?logo=scrapy&logoColor=white)](https://scrapy.org/)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Direct-indexing engine and quantitative portfolio replication calculator for the **Nigerian Exchange (NGX)**. Replicate high-performing Nigerian index funds in your personal brokerage (Bamboo, Chaka, Trove, Meritrade, CardinalStone) with **0% Management Expense Ratios (MER)**.

---

## 🎯 Problem & Value Proposition

Traditional Nigerian asset managers and mutual funds charge annual management fees ranging between **1.50% and 2.50%** alongside custody and trusteeship charges. Over a 10-year horizon, these fees consume up to 25% of compounding returns.

**NGX Index Fund Replicator** bypasses intermediary fee drag by giving retail investors, algorithmic traders, and family offices direct-indexing capabilities:
1. **Automated End-of-Day Scraping**: Captures official closing prices and market capitalizations directly from the Nigerian Exchange.
2. **Dynamic Capping & Index Weighting**: Enforces official NGX regulatory constituent weight caps (e.g., **30% single-stock cap for NGX Oil & Gas**, **15% cap for Afrinvest Dividend Yield Index**).
3. **Discrete Integer Share Optimization**: Converts arbitrary Naira budgets into exact whole-share purchase orders.
4. **Greedy Cash Sweep**: Systematically reallocates remaining uninvested cash into fractional-ready constituents down to `< min_share_price_with_fee`, eliminating cash drag.
5. **Real-World Brokerage Friction Modeling**: Factors in the mandatory **3.0% statutory Nigerian brokerage execution charges** (SEC fee, CSCS fee, NGX trading fee, stamp duty, VAT, and broker commissions).

---

## 🏛️ Supported Benchmark Indices

| Index ID | Benchmark Name | Single-Stock Cap | Benchmark Description |
| :--- | :--- | :--- | :--- |
| `oil_gas` | **NGX Oil & Gas Index** | 30.0% | Official market-cap-weighted index tracking petroleum and energy giants (SEPLAT, OANDO, TOTAL, CONOIL, MRS, etc.). |
| `afribank` | **Afrinvest Dividend Yield Index** | 15.0% | High-dividend yield portfolio screening top dividend-paying equities across banking, telecom, and consumer goods. |

*Additional custom or thematic indices can be registered via `index_funds/` JSON schemas.*

---

## ⚙️ Mathematical Formulation

### 1. Statutory Trading Fee Modeling
For each constituent stock $i$ with closing market price $P_i$ and statutory transaction fee rate $\tau = 3.0\%$:
$$\text{Effective Unit Cost}_i = P_i \times (1 + \tau)$$

### 2. Multiplier-Based Base Allocation
Given target investment capital $C$ and target benchmark weight $W_i$:
$$\text{Shares}_i = \left\lfloor \frac{C \times W_i}{\text{Effective Unit Cost}_i} \right\rfloor$$
$$\text{Total Invested} = \sum_{i} \left( \text{Shares}_i \times \text{Effective Unit Cost}_i \right)$$
$$\text{Residual Cash} = C - \text{Total Invested}$$

### 3. Guaranteed Greedy Cash Sweep
Any remaining cash balance is re-optimized iteratively:
1. Sort constituent equities by target weight priority and affordability:
   $$\text{Eligible Stocks} = \{ i \mid \text{Effective Unit Cost}_i \le \text{Residual Cash} \}$$
2. Allocate additional whole units to eligible stocks while maintaining portfolio weight harmony.
3. Terminate when $\text{Residual Cash} < \min_i(\text{Effective Unit Cost}_i)$.

---

## 🚀 Key Features

- **Executive Terminal UI**: Responsive, modern dark-themed dashboard featuring real-time portfolio metrics, statutory fee breakdowns, interactive asset allocation charts, and one-click copyable brokerage order tables.
- **Time-Locked Price Synchronization**: Scrapes updated end-of-day prices between **4:00 PM and 8:50 AM West Africa Time (WAT)**, preventing data corruption during active market trading hours (10:00 AM – 2:30 PM WAT).
- **Automated Render Cron Job**: Background worker schedules automatic daily crawler runs at 15:30 UTC (4:30 PM WAT) to keep constituent prices fresh after market close.
- **Safe Input Controls**: Prevents layout shift or UI distortion upon large number inputs (exponential notation protection and integer bounds).
- **SEO & Search-Ready**: Full OpenGraph meta tags, `robots.txt`, dynamic `sitemap.xml`, and branded SVG/ICO favicons.

---

## 📁 Repository Structure

```
indexCrawler/
├── app.py                      # FastAPI web server, REST API & routing
├── main.py                     # Discrete allocation algorithm & greedy cash sweep
├── crawler_runner.py           # Scrapy orchestration runner with error diagnostics
├── trigger_eod_crawl.py        # Automated cron endpoint runner for cloud schedulers
├── render.yaml                 # Render Blueprint (Web Service + Cron Job)
├── Procfile                    # Production startup command for Render
├── requirements.txt            # Python dependencies (FastAPI, Scrapy, Uvicorn, Brotli)
├── pyproject.toml              # Project packaging & metadata
├── index_funds/                # Index constituent data & Scrapy project
│   ├── oil_gas.json            # NGX Oil & Gas constituent prices & weights
│   ├── afribank.json           # Afrinvest Div Yield constituent prices & weights
│   ├── scrapy.cfg              # Scrapy configuration
│   └── index_funds/            # Spiders, pipelines, and browser-grade settings
│       ├── settings.py         # HTTP headers, Brotli decompression, stealth settings
│       └── spiders/
│           └── indexfunds.py   # Web scraper targeting ngxgroup.com
└── static/                     # Frontend dashboard assets
    ├── index.html              # Modern dark-mode terminal layout
    ├── style.css               # Production CSS design tokens & animations
    ├── app.js                  # Reactive state, calculation client & clipboard logic
    ├── favicon.ico             # Custom terminal favicon
    └── favicon.svg             # Vector icon
```

---

## 🛠️ Local Development & Quickstart

### Prerequisites
- **Python 3.11** or higher
- **Git**

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/abdulameen962/index-crawler.git
   cd index-crawler
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the local development server**:
   ```bash
   uvicorn app:app --reload --host 127.0.0.1 --port 8000
   ```

5. **Open the browser**:
   Navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## 🌐 API Reference

### 1. `GET /api/funds`
Returns the list of available index funds with metadata.
```json
[
  {
    "id": "oil_gas",
    "name": "NGX Oil & Gas Index",
    "filename": "oil_gas.json",
    "last_updated": "2026-09-20T16:00:00",
    "constituent_count": 7,
    "cap_percent": 30.0
  }
]
```

### 2. `POST /api/calculate`
Calculates optimal share quantities, cash utilization, and statutory transaction costs.

**Request Body**:
```json
{
  "fund_id": "oil_gas",
  "investment_amount": 500000.0,
  "transaction_fee_rate": 0.03
}
```

**Response**:
```json
{
  "fund_id": "oil_gas",
  "fund_name": "NGX Oil & Gas Index",
  "target_amount": 500000.0,
  "total_invested": 499120.45,
  "shares_cost": 484582.96,
  "transaction_fees": 14537.49,
  "remaining_cash": 879.55,
  "cash_drag_percent": 0.18,
  "orders": [
    {
      "symbol": "SEPLAT",
      "price": 5700.0,
      "shares": 26,
      "cost": 148200.0,
      "fee": 4446.0,
      "total_outlay": 152646.0,
      "target_weight": 30.0,
      "actual_weight": 30.58
    }
  ]
}
```

### 3. `GET /api/market-status`
Returns real-time NGX market hours, crawl window lock status, and last crawl execution status.

### 4. `POST /api/crawl`
Triggers an asynchronous scraping run. Available only during the EOD window (4:00 PM – 8:50 AM WAT).

---

## ☁️ Production Deployment on Render

This project includes a turnkey [`render.yaml`](render.yaml) Blueprint configuration that provisions both the **Web Service** and the daily **EOD Cron Job**.

### Automated Blueprint Deployment

1. Sign in to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** → **Blueprint**.
3. Connect your GitHub repository (`abdulameen962/index-crawler`).
4. Render will parse `render.yaml` and provision the **`ngx-index-calculator`** Web Service on the **Free Tier**.
5. Click **Apply** to deploy!

> **Automated EOD Price Sync**: Since Render requires a paid plan for cron jobs, an automated **GitHub Actions Workflow** (`.github/workflows/eod_crawl.yml`) runs Mon–Fri at 4:30 PM WAT (15:30 UTC) completely for free. It crawls fresh closing prices and auto-commits them, triggering Render's `autoDeploy`. Alternatively, you can use the **Sync EOD** button in the dashboard between 4:00 PM and 8:50 AM WAT.

---

## 💡 Brokerage Execution Advisory

- **Execution Timing**: Enter your replicated portfolio orders as **Limit Orders** immediately after market close (from 4:00 PM WAT onward) or at morning open (10:00 AM WAT). Avoid submitting market orders during low-liquidity midday windows.
- **Liquidity & Spread**: Always verify bid/ask depth on less liquid counters (e.g., MRS, CONOIL) before routing high-value orders.

---

## ⚖️ Disclaimer

**For Educational and Informational Purposes Only.**  
This tool and its calculated portfolios do not constitute financial, investment, legal, or tax advice. Market prices and index compositions are subject to market fluctuations. The authors and contributors assume no liability for financial gains, losses, slippage, or brokerage execution discrepancies resulting from the use of this software.

---

## 📬 Contact & Support

For inquiries, feature requests, or collaboration:
- **Maintainer**: Abdulameen
- **Email**: [abdulsanne1@gmail.com](mailto:abdulsanne1@gmail.com)
- **GitHub**: [@abdulameen962](https://github.com/abdulameen962)
