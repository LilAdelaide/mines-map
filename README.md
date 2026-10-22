# Australian Mines Map

Live map of ASX mining and energy companies: mines, mills, prices, gold costs, announcements and news.

**Use it:** open the site link on any device.
- **Android:** download `MinesMap.apk` from the newest Release and install it (allow "install unknown apps"), or in Chrome use ⋮ → *Install app*.
- **iPhone / iPad:** open the link in Safari → Share → *Add to Home Screen*.
- **Desktop:** open the link; in Chrome/Edge click the install icon in the address bar.

**Live data (free, no accounts):** `.github/workflows/data.yml` runs scripts in `scripts/` on GitHub's servers and commits fresh JSON to `data/`:

| Data | How often | Source |
| --- | --- | --- |
| ASX prices, market caps, announcements | Every 15 min while the ASX is open | ASX delayed quotes |
| Commodity ticker (gold, silver, copper, iron ore, oil, coal, uranium, AUD) | Hourly | gold-api.com, frankfurter.dev, Yahoo Finance, tradingeconomics |
| Headlines and price drivers | Every 30 min | Google News |
| 52-week ranges, volumes, yields, daily price history | After the close | ASX key statistics |
| Gold costs (AISC), calendar tidy-up | Weekday evenings | Company quarterly reports (ASX) |

Run any job now: Actions → *Live data* → Run workflow. Build a new APK: Actions → *Android APK* → Run workflow.
