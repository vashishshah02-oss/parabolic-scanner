# Parabolic Watch

A live morning screener for low-float stocks moving on abnormal volume — the
RETO / WHLR mechanic. Screens Finviz (float under 50M, relative volume ≥ 3×,
up ≥ 15% on the day), cross-checks every candidate against Yahoo Finance for
a real average-volume baseline and how far it's slipped off today's high,
and classifies each as **Extended**, **Reversing**, or **Faded**.

It runs itself: a GitHub Action re-runs the scan every weekday morning and
commits the fresh results, so the page is already up to date when you open
it — nothing to click.

## How it's put together

- `scan.py` — does the actual screening and writes `data/latest.json`
- `index.html` — static page that reads that JSON and renders it (no build step, no framework)
- `.github/workflows/scan.yml` — the scheduled job that runs `scan.py` and commits the result

## Run it locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 scan.py            # writes data/latest.json
python3 -m http.server 8000   # then open http://localhost:8000
```

## Ship it (GitHub Pages, free)

```bash
git init                     # already done for you
git add -A
git commit -m "Initial commit"
gh repo create parabolic-scanner --public --source=. --push
# or, without the gh CLI: create a repo on github.com, then
git remote add origin https://github.com/<you>/parabolic-scanner.git
git branch -M main
git push -u origin main
```

Then in the repo's **Settings → Pages**, set the source to the `main`
branch, root folder. Your live scanner will be at
`https://<you>.github.io/parabolic-scanner/`.

The scheduled workflow needs no secrets or API keys — Finviz and Yahoo
Finance are both queried anonymously. It's enabled automatically once the
workflow file is pushed; you can also trigger it manually from the
**Actions** tab (**Run parabolic scan → Run workflow**) to get a fresh
result immediately instead of waiting for the next scheduled run.

## Known limitations

- Finviz and Yahoo Finance are both **unofficial/scraped** sources — they
  can change shape or rate-limit without notice. If a scheduled run fails,
  check the Actions tab first.
- Float figures come from Finviz's own screener and aren't independently
  re-verified per ticker.
- This is pattern-tracking for research, not investment advice — verify
  everything against your own broker before acting on it.
