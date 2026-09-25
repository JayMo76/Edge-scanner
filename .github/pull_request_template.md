## What this changes

<!-- What and why, in a few sentences. Link the issue if there is one. -->

## How it was tested

<!-- Commands run, and what you checked by hand. -->

- [ ] `python -m pytest` passes
- [ ] `npm --prefix dashboard-v2 run lint` and `npm --prefix dashboard-v2 run build` pass
- [ ] New trigger, condition or indicator? Tests include the bar it must NOT fire on
- [ ] Dashboard change? Screenshot attached

## Worth knowing for review

- [ ] New dependency (which, and why)
- [ ] New network call, open port, or background job
- [ ] A second market-data connection (Alpaca allows only one per account)
- [ ] File access outside the app folder
- [ ] Change to saved files (screens, setups, filters, caches) that existing installs must migrate
- [ ] None of the above

No API keys, `.env` files, `data/` contents or account details are included.
