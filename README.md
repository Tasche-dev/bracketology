# Bracketologist Pro: daily auto-refresh

Every morning (about 6 AM Central) GitHub runs `update.py`, which pulls KenPom and EvanMiya into `data.json`
and republishes the site. `index.html` reads `data.json` and rebuilds the field, so new teams enter and
others drop out as ratings and records change.

## Turn it on (about 10 minutes)
1. Create a free GitHub account and a new repository (public is simplest).
2. Upload everything in this folder, including the hidden `.github` folder. Easiest: on the repo page choose
   Add file > Upload files and drag in the unzipped contents.
3. Repo Settings > Secrets and variables > Actions > New repository secret. Add two:
   `KENPOM_EMAIL` and `KENPOM_PASSWORD` (your KenPom login; needs an active subscription).
   Keep the repo's secrets private. Do not put these in any file.
4. Repo Settings > Pages > Source: choose "GitHub Actions".
5. Actions tab > "Refresh bracket" > Run workflow. Check the first run's log. It prints how many teams
   matched from EvanMiya and lists any unmatched names.
6. Your site appears at https://YOUR-USERNAME.github.io/YOUR-REPO/ (the finished run shows the link).
   After that it refreshes by itself every morning. The Run workflow button also refreshes on demand.

## Keeping bracketology.netlify.app
In Netlify, add a new site from this GitHub repo (no build command, publish directory `.`). Netlify
redeploys every time the bot saves new data. To reuse the old name, rename or delete the old site first.

## If something breaks
- A source that fails keeps its last numbers, and the page says so. Both failing stops the run (red X in Actions).
- KenPom login or column changes: edit `kenpom()` in `update.py`.
- EvanMiya page layout changes: edit `evanmiya()`. Mismatched team names: add to `ALIASES`.
- The cron time is in `.github/workflows/refresh.yml` (GitHub uses UTC).
