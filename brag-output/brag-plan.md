# Brag Plan: ReconMatch

## Step 1 rubric

1. **What is the app?** A deterministic matcher that pairs bank-statement lines with ledger entries, scores each match with its rule and confidence, and labels every leftover as a break with a fix hint.
2. **Funniest or most impressive claim.** On 32,048 held-out BenchRec records it scores 88.65% against 62.45% for the published MatcherByChatGPT reference, and 70.43% against 0.00% on split payments. Then the README retires its own auto-match claim because the pre-set 99.8% bar was not met.
3. **Visual hook.** Sample batch S0007: one `NEFT BATCH SETTLEMENT` line for −2,152,411.81 that is exactly three ledger entries (E0007 + E0008 + E0009). Three rows snapping into one reads at a glance.
4. **What to show from the real UI.** The Gradio "Sample (precomputed)" tab: the "Load sample reconciliation" button, the summary line (`42/46 ledger entries auto-matched (91%) · 8 breaks flagged · 43 statement lines`), and the Matches table with its Tier and Confidence columns.
5. **Shortest satisfying video.** About 22s. The hook, the app, one break, the benchmark, and the retraction each need a readable hold.
6. **Tone.** Preset `polished`. Direction: "an audit report that fact-checks itself".
7. **Audio feel.** A steady, clean bed (vol-12) at low volume. A few dry, precise cues: row snaps, one click, a firm stamp, a soft outro bell.
8. **Share caption.** See the draft below.
9. **User flow.** Open the Sample tab, click "Load sample reconciliation", read the summary and matches, scan the breaks. The upload flow ("Reconcile your own") has the same result view.

## What is this app?
ReconMatch matches bank-statement lines to ledger entries with fixed rules (exact, date-windowed, split, batch), so the same inputs always give the same output. The impressive part is the benchmark. The unusual part is that it publishes the claim it could not back.

## The angle
A brag delivered like an audit. Every number on screen comes from the repo (sample report, frozen eval, README). The video builds up the wins and then shows the line most launch videos would hide: the auto-match bar was set before the run, the run missed it, and the claim was retired. The retraction is the punchline and the flex.

## Hook (first 2-3 seconds)
One bank line, `NEFT BATCH SETTLEMENT −2,152,411.81`, sits alone on the right. A serif line reads "The bank saw one payment." Three ledger rows drop in on the left with "Your ledger booked three." Lines draw from each row into the bank line, a running sum lands on −2,152,411.81, and a `TIER 4 · BATCH` tag locks the match.

## Key moments (the middle)
- The Gradio app loads the sample. A cursor clicks the orange button, the summary line appears, and match rows cascade in with tier numbers 1, 2 and 4. The E0007, E0008, E0009 → S0007 row from the hook is visible in the table.
- One break up close. Ledger E0010 −864,119.90 against statement S0008 −861,419.90. The swapped digits `4,1` / `1,4` light up, the `amount_mismatch_suspect` tag lands, and the app's own hint reads "check for a keying error or an absorbed fee".
- Someone else's data. BenchRec cash v1.0, 32,048 held-out records. Two bars grow: ReconMatch 88.65% and MatcherByChatGPT 62.45%. A second row shows split payments: 70.43% against 0.00%.

## Outro / punchline
Hard cut to a quiet frame: "Auto-match bar, set before the run: 99.8% precision." A red `NOT MET` stamp lands. "Claim retired." Then the wordmark, "Same inputs, same output.", and the live URL.

## User flow worth showing
Sample tab → click "Load sample reconciliation" → summary and matches table fill in → breaks explain the leftovers. Scenes 2 and 3 carry this flow.

## Tone
- Preset: polished
- Creative direction: an audit report that fact-checks itself
- Interpretation: few elements per scene and long holds on numbers, with motion that is precise rather than bouncy. The single dry joke (the stamp) gets a hard cut and a pause, and nothing winks at the viewer.

## Format: landscape · 1920x1080
## Duration: 22.8s

## Visual identity (from the project)
The app is a stock Gradio `gr.Blocks` (Default theme: orange primary, zinc neutrals). The video uses the Gradio dark look, with neutrals tinted slightly warm.
- Background: #0f0d0b (warm near-black, from Gradio dark neutral-950 #09090b)
- Panels: #1a1714, borders #2f2a25
- Accent: #f97316 (Gradio primary orange-500), soft accent #fdba74
- Text: #f4efe9, muted #a8a097
- Semantic break red (breaks and the stamp only): #f87171
- Display font: Newsreader (serif, "published report" voice for statements)
- Data font: IBM Plex Mono (Gradio's own mono) for IDs, amounts, tiers and metrics
- UI mockup font: Source Sans 3, only inside the recreated Gradio window, because that is what the live app renders
- Excluded fonts (user request): Space Grotesk, Playfair Display, Figtree, Archivo (and Archivo Black), Inter
- Strongest visual element: the Matches table with Tier/Confidence columns, and the batch row that turns three entries into one line

## Share copy (draft)
ReconMatch pairs bank lines with ledger entries using fixed rules and no model. On 32,048 held-out BenchRec records it gets 88.65% exactly right, against 62.45% for the published ChatGPT matcher. I also set a 99.8% auto-match bar before the run, it missed, so I retired that claim.

## Audio direction
- Role: sparse professional accents over a low, steady bed
- Music: happy-beats-business-moves-vol-12 (steady and clean, 109.96 BPM)
- Music treatment: starts at 0 at about 0.30 volume, stays level, fades out over the last ~1.2s under the wordmark
- Music cue guidance: preset `assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`. Strong cues to target: 13.11s (benchmark bars start), 18.56s (NOT MET stamp). Beat grid for the three hook rows: 1.64 / 2.19 / 2.73. The table cascade may use 6.56 → 7.09 as start/end accents.
- Audio-reactive treatment: subtle. Bass energy makes the warm orange background glow breathe. No waveform or equalizer visuals.
- SFX posture: sparse, motion-matched
- Audio-coupled moments: hook rows landing, the match lock, the cursor click, bars growing, the stamp, the wordmark
- Restraint rule: no SFX on every table row, no whooshes on crossfades, nothing louder than the stamp

## Storyboard

### Scene 1 · One payment, three entries · 4.4s (0.0–4.4)
Statement card slides in on the right (`BANK STATEMENT`, S0007, 2026-03-04, NEFT BATCH SETTLEMENT, −2,152,411.81). Serif headline top-left: "The bank saw one payment." Three ledger rows (E0007 Metro Property Rentals −638,787.31, E0008 Iris Marketing Group −715,032.43, E0009 Global Talent Payroll −798,592.07) drop in on the left, and the headline gains "Your ledger booked three." Connector lines draw from each row to the card. The sum counts to −2,152,411.81 and a `TIER 4 · BATCH` tag locks on.
Sequential/interaction: yes. Three rows arrive one by one on beats (short labels, then all held ≥1.5s).
Audio intent: calm, precise start
Audio-coupled idea: soft card-place per row, one clean lock accent on the match
Music: steady bed begins
Transition mood: soft crossfade with a slight push-in → Scene 2

### Scene 2 · The app · 4.6s (4.4–9.0)
Recreated Gradio window in a browser frame (URL `reconmatch-aa9c.onrender.com`). Title "ReconMatch", tabs "Sample (precomputed)" and "Reconcile your own", orange "Load sample reconciliation" button. A cursor clicks it. The summary line appears: **42/46** ledger entries auto-matched (**91%**) · **8** breaks flagged · 43 statement lines. The first eight Matches rows cascade in from the real report (tiers 1, 1, 1, 1, 1, 1, 4, 2), and the E0007, E0008, E0009 → S0007 batch row lights up on the 7.64s beat. The camera eases toward the summary.
Sequential/interaction: yes. Simulated click, then a fast row cascade held ≥2s.
Audio intent: tactile
Audio-coupled idea: one mouse click on press; a light accent at cascade start only
Transition mood: clean crossfade → Scene 3

### Scene 3 · A break, explained · 3.8s (9.0–12.8)
Headline: "What doesn't match gets a reason." Two amount rows: `LEDGER E0010 −864,119.90` over `STATEMENT S0008 −861,419.90`. The transposed digits highlight in red and a small swap mark connects them. Tag `amount_mismatch_suspect`, then the app's hint in mono: "check for a keying error or an absorbed fee". A footer strip lists all 8 sample breaks by category (2 amount_mismatch_suspect, 1 duplicate_suspect, 2 missing_in_ledger, 3 missing_in_statement).
Sequential/interaction: yes. Amounts, then highlight, then tag and hint (each held ≥0.8s; hint held ≥1.2s).
Audio intent: a small "found it" moment
Audio-coupled idea: one light tick when the digits highlight
Transition mood: slide → Scene 4

### Scene 4 · Someone else's data · 4.4s (12.8–17.2)
Mono eyebrow: `BENCHREC CASH v1.0 · 32,048 HELD-OUT RECORDS · STRICT EXACT-SET`. Serif headline: "Someone else's data." Two horizontal bars grow as the numbers count up: ReconMatch 88.65% (orange), MatcherByChatGPT (published reference) 62.45% (muted). A second, smaller pair: split payments (multi-A) 70.43% against 0.00%.
Sequential/interaction: yes. Bars grow on the 13.11s strong cue, then the multi-A row follows; all held ≥1.8s.
Audio intent: confident lift
Audio-coupled idea: bar growth with a soft rising accent; nothing on the counters
Transition mood: hard cut → Scene 5

### Scene 5 · The retraction · 3.0s (17.2–20.2)
Quiet frame. Serif line: "Auto-match bar, set before the run: 99.8% precision." A red `NOT MET` stamp lands on the 18.56s strong cue. Beneath it: "Claim retired." Small mono footnote: `held-out coverage at 99.8%: 6.80%`.
Sequential/interaction: yes. Line, stamp, then the retirement line (held ≥1.0s).
Audio intent: dry, firm
Audio-coupled idea: one heavy soft thud on the stamp
Transition mood: soft crossfade → Scene 6

### Scene 6 · Outro · 2.6s (20.2–22.8)
Wordmark "ReconMatch" (Newsreader), tagline "Same inputs, same output.", URL `reconmatch-aa9c.onrender.com` in mono. Hold to the end.
Sequential/interaction: none
Audio intent: resolve
Audio-coupled idea: a soft bell under the wordmark; music fades
Transition mood: end on the held wordmark

**Music mood for this video:** steady, clean, understated
**Audio summary:** a low steady bed with a handful of precise ticks and clicks, one firm stamp, and a soft resolve under the wordmark.
