# Hyperframes Composition Brief: ReconMatch

## Objective
Create a short launch-style brag video for ReconMatch.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape, 1920x1080
- Duration: 22.8 seconds

## Source Material
- Project root: `/home/parvez/Projects/reconmatch`
- Primary files read: `README.md`, `app.py`, `samples/report.json`, `samples/ledger.csv`, `samples/statement.csv`, `data/benchrec/artifacts/frozen_eval.md`, `DEPLOY.md`, `pyproject.toml`, Gradio Default theme (`.venv/.../gradio/themes/default.py`)
- Product name: ReconMatch
- Tagline / strongest claim: "Deterministic: same inputs, same output, zero inference cost." BenchRec held-out: 88.65% vs 62.45% (MatcherByChatGPT), multi-A 70.43% vs 0.00%. Auto-match bar (Wilson LB ≥ 99.8%) not met, so no auto-match is claimed.
- Key UI to recreate: the Gradio "Sample (precomputed)" tab with the "Load sample reconciliation" button, the summary markdown, and the Matches dataframe (`Ledger entries | Statement line(s) | Tier | Confidence`).
- Copy that must appear verbatim:
  - `42/46 ledger entries auto-matched (91%) · 8 breaks flagged · 43 statement lines`
  - `Load sample reconciliation`
  - `amount_mismatch_suspect`
  - `check for a keying error or an absorbed fee`
  - `NEFT BATCH SETTLEMENT`
  - `reconmatch-aa9c.onrender.com`

Real data used (from `samples/report.json` and the CSVs):
- Batch: E0007 Metro Property Rentals −638,787.31 + E0008 Iris Marketing Group −715,032.43 + E0009 Global Talent Payroll −798,592.07 = S0007 NEFT BATCH SETTLEMENT −2,152,411.81 (2026-03-04), tier 4, confidence 0.53
- First ten match rows in report order: E0001/S0001 t1 0.95 · E0002/S0002 t1 0.95 · E0003/S0003 t1 0.95 · E0004/S0004 t1 0.95 · E0005/S0005 t1 0.95 · E0006/S0006 t1 0.95 · E0007, E0008, E0009/S0007 t4 0.53 · E0011/S0009 t2 0.753 · E0012, E0013, E0014/S0010 t4 0.526 · E0015/S0011 t2 0.734
- Break: E0010 ledger −864119.9 vs S0008 statement −861419.90 (digits 4,1 transposed)
- Retraction footnote: best held-out coverage clearing 99.8% is 6.80%

## Creative Direction
- Tone preset: polished
- Creative direction: an audit report that fact-checks itself
- Interpretation: sparse frames, long holds on numbers, precise motion (expo/power eases, no elastic). One dry joke (the stamp) gets a hard cut and a beat of stillness.
- Angle: a brag delivered like an audit. Every number is traceable to the repo. The wins build up, then the video shows the retired auto-match claim as the punchline.
- Hook: one bank line, three ledger rows, lines drawing into a single match with `TIER 4 · BATCH`.
- Outro / punchline: `NOT MET` stamp, "Claim retired.", then the wordmark with "Same inputs, same output." and the URL.
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign
  - The fonts Space Grotesk, Playfair Display, Figtree, Archivo (including Archivo Black) and Inter, anywhere, including fallbacks and aliases (Helvetica/Arial alias to Inter in the renderer, so do not list them)

## Visual Identity
- Background: #0f0d0b (warm-tinted Gradio dark neutral)
- Panels: #1a1714; borders #2f2a25
- Text: #f4efe9; muted #a8a097
- Accent: #f97316 (Gradio Default primary, orange-500); soft #fdba74
- Break red (breaks and stamp only): #f87171
- Display font: Newsreader (local woff2 via @font-face)
- Data font: IBM Plex Mono (local woff2 via @font-face)
- UI mockup font: Source Sans 3, only inside the Gradio window mockup (the live app renders Source Sans Pro)
- Visual references from the project: Gradio dark block panels with rounded corners, orange primary button, dataframe grid, markdown summary with bold figures

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract.

Scene summary:
1. One payment, three entries · 4.4s · statement card, three ledger rows, connectors, sum, `TIER 4 · BATCH`
2. The app · 4.6s · Gradio window, cursor click, summary line, match rows cascade
3. A break, explained · 3.8s · transposed digits, `amount_mismatch_suspect`, hint text
4. Someone else's data · 4.4s · BenchRec eyebrow, 88.65% vs 62.45% bars, 70.43% vs 0.00%
5. The retraction · 3.0s · 99.8% bar line, `NOT MET` stamp, "Claim retired."
6. Outro · 2.6s · wordmark, tagline, URL

## Audio
- Audio role: sparse professional accents over a low bed
- Audio arc: steady bed from 0s, precise accents on the match, click, bars and stamp, soft bell at the wordmark, fade under the end
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`
- Music treatment: volume ~0.30, fade to 0 over the last ~1.2s
- Music cue guidance: preset `assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json` (109.96 BPM). Strong cues: 13.11s (bars), 18.56s (stamp). Beats for hook rows: 1.64, 2.19, 2.73.
- Audio-reactive treatment: subtle. Bass energy drives the opacity/scale of the warm background glow. No visualizer graphics.
- Audio-coupled moments:
  - Scene 1 rows · soft drop per row; match lock · warm bong
  - Scene 2 button press · click
  - Scene 3 digit highlight · light click
  - Scene 4 bars start · soft medium impact
  - Scene 5 stamp · heavy soft impact
  - Scene 6 wordmark · heavy bell, low volume
- SFX selection guidance: prefer low/medium HF-risk files (interface/drop, interface/bong_001, interface/click_003, ui/click2, impactSoft_*, impactBell_heavy_000)
- SFX analysis guidance: `~/.claude/plugins/cache/brag/brag/0.2.2/skills/brag/assets/sfx/sfx-analysis.md`
- Exact SFX choice: Hyperframes chooses files, timestamps, density and volume from the implemented animation.
- Audio files: copy the chosen music and SFX into `brag-output/composition/assets/`

## Hyperframes Instructions
Load `hyperframes-core`, `hyperframes-animation`, `hyperframes-creative`, `hyperframes-keyframes` and `hyperframes-cli`. /brag is its own workflow, so skip the `hyperframes` entry-point interview. Prefer native Hyperframes conventions over anything in `/brag`.

Requirements:
- Show at least one real UI, copy, or visual element from the source project.
- Keep all text readable in the final render.
- Keep the video within 15-25 seconds.
- Include the planned music/SFX layer.
- Treat `/brag` audio notes as guidance and choose SFX after the animation exists.
- Treat music cues as optional timing hints; major reveals within ±0.15s of a strong cue, small entrances within ±0.10s of a beat.
- Audio-reactive: pre-extract audio bands and drive a subtle existing element (background glow).
- Use local assets for audio, fonts and runtime where possible.
- Run `hyperframes check` before render.
