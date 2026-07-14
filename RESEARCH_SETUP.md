# Evidence Research Setup

Copy the `research` folder, `ai_report.py`, and `research_worker.py` into the
project root.

Add these packages to `requirements.txt`:

```text
requests
pydantic>=2
```

`google-genai` and `python-dotenv` should already be present.

## Required environment variables

```text
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3-flash-preview
SEC_USER_AGENT=YourAppName your-real-email@example.com
```

The SEC asks automated clients to identify themselves. Use a real contact
email in `SEC_USER_AGENT`.

## Optional environment variables

```text
FRED_API_KEY=...
COMPANY_IR_URLS_JSON={"MU":["https://investors.micron.com/"]}
RESEARCH_WATCHLIST=MU,AMD,NVDA
```

Without `FRED_API_KEY`, macro data is skipped safely.

## Current behavior

- Collects recent SEC filing records.
- Collects selected SEC XBRL company facts.
- Discovers recent news headlines through GDELT.
- Accepts optional official investor-relations URLs.
- Validates source quality, freshness, and coverage.
- Sends the structured evidence to Gemini without paid Google Search
  grounding.
- Requires source IDs beside factual statements.

## Important limitations

- GDELT results are headline metadata, not verified full-article facts.
- Generic investor-relations page parsing is not included because company
  websites differ substantially.
- SEC XBRL facts require careful period and unit interpretation.
- This is research software, not a guarantee of accuracy or returns.
- Keep real trade execution disabled until extensive walk-forward testing.
