# Deploy checklist (Parvez-owned steps)

Everything below is the only remaining work on Artifact 3. Code is complete:
45 tests green, ruff clean, Gradio app verified end-to-end (2026-07-18).

## 1. Create the GitHub repo and push (~2 min) — ✅ DONE 2026-07-18, CI green

```bash
cd ~/Projects/reconmatch
gh repo create Sero01/reconmatch --public --source=. --push
```

(Or create it in the GitHub UI, then `git remote add origin ... && git push -u origin master`.)

CI (`.github/workflows/ci.yml`) is fully offline/deterministic — no secrets or
env vars needed. It should go green on the first push.

## 2. Create the Render service (~3 min) — ✅ DONE 2026-07-18: https://reconmatch-aa9c.onrender.com

Same flow as DocVal (docval-yy4s):

1. Render dashboard → New → Blueprint → select `Sero01/reconmatch`.
2. `render.yaml` is at the repo root; accept defaults. **No env vars needed**
   (no API key — the app is pure Python, no LLM calls).
3. Free tier is fine. Remember the quirks from DocVal: instance sleeps after
   ~15 min idle (~1 min wake), and during rollouts two backends alternate
   404/200 — wait it out before judging health.

## 3. Tell Claude the URL — ✅ DONE 2026-07-18

URL recorded in README + DocVal cross-link; production sample + upload flows
verified via gradio_client (36/40 auto-matched on the bundled sample).
Checklist complete — Artifact 3 is shipped.
