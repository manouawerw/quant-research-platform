# Watchlist Scanner Setup

## Files

Add:

- `watchlist_scanner.py`
- `watchlist_worker.py`

Replace:

- `database.py`
- `app.py`

## Local test

```powershell
streamlit run app.py
```

Open the `Watchlist Scanner` page, enter up to 50 tickers, and run a scan.

## Worker test

Set a watchlist in `.env`:

```text
RESEARCH_WATCHLIST=MU,AMD,NVDA,AAPL,MSFT,GOOGL,META,AMZN,TSM,AVGO
WATCHLIST_BENCHMARK=SPY
```

Run one scan:

```powershell
python watchlist_worker.py
```

For a continuously running worker:

```text
WATCHLIST_RUN_FOREVER=true
WATCHLIST_INTERVAL_SECONDS=300
```

Then run:

```powershell
python watchlist_worker.py
```

## Railway

Create a second Railway service from the same GitHub repository.

Use this start command:

```text
python watchlist_worker.py
```

Add the same variables used by the dashboard:

- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `DATABASE_URL`
- `RESEARCH_WATCHLIST`
- `WATCHLIST_BENCHMARK`
- `WATCHLIST_RUN_FOREVER=true`
- `WATCHLIST_INTERVAL_SECONDS=300`

The worker saves scan results to PostgreSQL. The Streamlit dashboard reads the
latest completed scan.

The worker does not place trades.
