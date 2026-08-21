# Pushing this to GitHub + Vercel

Everything is committed on branch `main` already — one commit, no remote set.

## 1. Push

```bash
unzip fpl-dashboard.zip && cd fpl-dashboard
git remote add origin https://github.com/JNBO2026/fpl-dashboard.git
git push -u origin main
```

If the repo already has a README, add `--force` to that last command (your local
history is the one you want).

## 2. Deploy

Go to https://vercel.com/new, import `fpl-dashboard`, and hit Deploy.

- Framework preset: **Other**
- Build command: leave empty
- Output directory: leave empty
- Install command: leave empty

It's a static site — `index.html` is pre-rendered and committed, so there is nothing
to build. Every push to `main` redeploys automatically.

## 3. Refresh the data

```bash
./build.sh          # pulls live FPL data, rebuilds index.html + data.json
git add -A && git commit -m "data: refresh" && git push
```

The included GitHub Action does this twice a day on its own, so the page stays
current between deadline reviews. It needs no secrets — the FPL API is public.
