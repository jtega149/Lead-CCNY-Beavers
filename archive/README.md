# Archive

This directory contains initial exploratory prototypes created prior to `Product.md`:
- `disputes_api.py` — earlier rule-based dispute routing
- `purchase_confirmation.py` — two-step proposal and hash confirmation flow
- `index.html` — original standalone UI; its scoring and dispute logic ran in the browser (a JS copy of `friendly_fraud.py`) and never called the API
- `friendly_fraud.py` — statistical behavioral fraud scoring heuristics

The active architecture follows `Product.md` with `app.py` as the unified service entry point.
