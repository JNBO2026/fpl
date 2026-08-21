# AI FC — Fantasy Premier League control room

A mobile-first dashboard showing the current squad **and the evidence behind every
decision** — player-level expected goals and assists, defensive-contribution rates,
clean-sheet probabilities, fixture difficulty, ownership and transfer-market flow.

Built so that when a transfer recommendation arrives, the reasoning is one tap away
rather than buried in a chat log.

## How it works

```
build_data.py   →  data.json    pulls the live FPL API, runs the projection model
render.py       →  index.html   inlines data.json into template.html
```

`index.html` is fully self-contained — no runtime API calls, no CORS problems, no
build step on the host. Vercel just serves the file.

Refresh everything:

```bash
./build.sh
```

Committing the regenerated `data.json` and `index.html` triggers a Vercel redeploy.
Because `data.json` is committed each time, git history doubles as a permanent record
of exactly what the model saw before each deadline.

## The model

For every player, expected FPL points per 90 are derived from underlying numbers
rather than points scored:

| Component | Source |
|---|---|
| Goals | `expected_goals_per_90` × 10 / 6 / 5 / 4 by position |
| Assists | `expected_assists_per_90` × 3 |
| Clean sheet | `exp(-expected_goals_conceded_per_90)`, × 4 for GK/DEF, × 1 for MID |
| Saves | `saves_per_90 / 3` for keepers |
| Defensive contribution | Poisson P(X ≥ 10) for defenders, P(X ≥ 12) for outfielders |
| Bonus | scaled from BPS rate |

That is blended with actual points per 90, weighted by sample size, then scaled by
expected minutes, availability and fixture difficulty over the next six gameweeks.

As the season progresses, weight shifts onto current-season data
(`min(0.8, gameweeks_played / 12)`), and from gameweek 7 static fixture-difficulty
ratings give way to each club's rolling expected goals scored and conceded.

## Files

| File | Purpose |
|---|---|
| `template.html` | The page. Edit this, not `index.html`. |
| `build_data.py` | Fetches the API, runs the model, writes `data.json`. |
| `render.py` | Inlines `data.json` into the template. |
| `decisions.json` | The decision log — appended, never rewritten. |
| `index.html` | Generated. Committed so Vercel can serve it directly. |
| `data.json` | Generated. Committed as the audit trail. |

## Updating the squad

Edit `SQUAD`, `CAPTAIN`, `VICE` and `BENCH_ORDER` at the top of `build_data.py`,
add an entry to `decisions.json`, then run `./build.sh`.

## Deploying

Import the repo at [vercel.com/new](https://vercel.com/new). No framework, no build
command, no output directory — it is a static site. Every push to `main` redeploys.

A GitHub Action (`.github/workflows/refresh.yml`) also refreshes the data twice daily
so the page stays current between deadline reviews.

## Caveats

Projections are estimates built on last season's numbers plus this season's sample.
They do not know about tactical changes, a manager's mood, or a fitness test that
happens an hour before kick-off. Confirmed lineups are published after the FPL
deadline, so nobody — including this — has them in time.
