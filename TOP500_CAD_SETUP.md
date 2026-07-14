# Top 500 + CAD-Hedged CDR Scanner

## Add these files

```text
universe.py
bulk_market_data.py
cad_cdr.py
universe_scanner.py
universe_database.py
universe_worker.py
pages/1_Top_500_Scanner.py
data/cdr_underlyings.csv
```

This package adds a Streamlit multipage scanner. It does not replace your
existing `app.py`.

## Add requirements

```text
lxml
html5lib
beautifulsoup4
yfinance
requests
```

Then install:

```powershell
python -m pip install -r requirements.txt
```

## Run a manual scan

```powershell
streamlit run app.py
```

Open **Top 500 Scanner** from the Streamlit page navigation.

## Test the worker once

```powershell
python universe_worker.py
```

## Railway worker variables

```text
UNIVERSE_BENCHMARK=SPY
UNIVERSE_RUN_FOREVER=true
UNIVERSE_INTERVAL_SECONDS=300
CDR_LOOKUP_TOP_N=25
```

Create a second Railway service from the same repository with start command:

```text
python universe_worker.py
```

Give it the same Alpaca and database variables as the dashboard.

## Important design notes

- The scanner fetches historical bars in batches.
- The entire universe is scored with Python. Gemini is not called 500 times.
- CDR lookups are performed only for the highest-ranked names.
- The constituent list is cached for 24 hours.
- You may provide a licensed constituent CSV with:

```text
UNIVERSE_CSV_URL=https://...
```

Required CSV columns:

```text
ticker,company_name,sector,sub_industry
```

## CAD-hedged CDR handling

A CDR is not simply the U.S. price converted at USD/CAD. It represents a
fractional interest and uses a notional currency hedge. The code:

1. Finds a configured CDR mapping.
2. Retrieves an available CAD quote.
3. Calculates the observed CDR/underlying price ratio.
4. Translates the underlying model ranges using that observed ratio.

This remains approximate because the ratio changes over time and free quotes
may be delayed. Confirm symbols and executable prices with your broker.
