---
name: "do-fundo-do-poco-interactive-deck"
description: "Build an interactive web pitch deck (single HTML, live demos, presenter HUD, PDF export with keyframes) in the Do Fundo do Poço \"Ascensão\" identity, packaged for the host the team chooses. Use for any Do Fundo do Poço / hackathon presentation."
---

# Interactive deck — Do Fundo do Poço (hackathon, identidade "Ascensão")

Use when anyone on the team asks for a presentation, pitch or demo deck for the **Do Fundo do Poço** team (hackathon: engineering problems solved with AI). It builds a web deck with presenter HUD, keyframe PDF export and deploy packaging, in the Do Fundo do Poço identity with pitch-length timing. If the team wants slides to edit by hand instead, point to `design/apresentacoes/google-slides/` (a .pptx template to import into Google Slides).

## 0. Load the identity first (folders win over this file)

In this repository:
- `design/apresentacoes/README.md` — the presentation identity: concept, layouts, classes, HUD, timing table.
- `design/apresentacoes/template/` — the starter deck (`index.html` with the full engine, fonts and logos embedded inline; `fonts/`, `assets/logo/` originals; `vercel.json`; `demo_check.py`). **Always start a new deck by copying this folder**, never from scratch.
- `design/design-system/README.md` — color and type tokens (source of truth for values); `assets/logo/` holds the vector logo kit (`01`–`13_*.svg`, `LEIA-ME.txt`).

Read both READMEs and the template before writing anything. If they are unreachable, use the snapshot below, say so in one line, and rebuild the engine from section 3.

Snapshot:

```css
/* brand: verde-escuro #102C26 · esmeralda #16C784 · off-white #F5F3ED · apoio #0D4939 */
/* light "superfície" — DEFAULT for projection */
--ink:#F5F3ED; --surface:#FFFFFF; --surface-2:#E3DED2; --text:#102C26; --text-muted:#4F5E57;
--verde:#0A6E48; --verde-glow:#085A3B; --esmeralda:#16C784; --on-esmeralda:#102C26;
--profundo:#102C26; --apoio:#0D4939; --on-profundo:#F5F3ED; --alerta:#B3261E; --info:#1D5FA6;
--serie-1:#0C8A5A; --serie-2:#102C26; --serie-3:#1D5FA6; --serie-4:#8A9690;
/* dark "fundo do poço" */
--ink:#102C26; --surface:#173B33; --surface-2:#24503F; --text:#F5F3ED; --text-muted:#A9BDB3;
--verde:#16C784; --verde-glow:#43D79B; --profundo:#0D4939; --alerta:#FF8A7A; --info:#8CBCF5;
--serie-1:#16C784; --serie-2:#F5F3ED; --serie-3:#8CBCF5; --serie-4:#5F8A73;
/* shape */
--radius-sm:6px; --radius-md:12px; --radius-lg:24px; --radius-pill:999px;
/* type: one family */
--font-display:'Montserrat',system-ui,sans-serif; /* 800, display/H1 UPPERCASE */
--font-body:'Montserrat',system-ui,sans-serif;
--font-mono:'IBM Plex Mono',ui-monospace,monospace; /* readouts, code, footer only */
--tracking-display:-0.01em; --tracking-kicker:0.5em; --tracking-eyebrow:0.08em;
```

Fonts and logos are **embedded in `index.html`** (base64 woff2, inline SVG in `<template>`s) so the deck works offline at the venue and inside sandboxed previews. Keep it that way: no relative `src`/`href` that the deck depends on.

Identity rules that apply to slides:
- **Light theme by default** (`<html data-theme="light">`); dark via key `D` or `prefers-color-scheme` when `data-theme` is removed. Dividers are always dark. PDF export forces light.
- **Esmeralda is shape, not text, on light** (#16C784 on #F5F3ED = 1.98:1): arrow, curves, bars, the 56×4 rule, CTA fill. Green text is `--verde`. The CTA reads `--on-esmeralda` (verde-escuro) in both themes; never white on esmeralda.
- **One highlight per slide**: a `--profundo` block (`.card.hi`) or one big `--verde` number. `--alerta` at most once, always with a word.
- **Flat and rounded**: cards `--radius-md`, panels `--radius-lg`, no borders, no shadows, no gradients.
- **Eyebrow** = the board's "01 / ASCENSÃO": `<p class="eb"><b>01</b> / Rótulo</p>` — Montserrat 800 uppercase, number in `--verde`, esmeralda rule under it (CSS adds it).
- **Concept "ascensão"**: the kit's curves (`10_elemento_curvas`, `12_fundo_apresentacao`) enter from a corner and bleed off the slide — on the cover and on every divider. Each divider shows **the climb**: a rail with one step per section and the kit's arrow (`09_seta`) on the current section's step. The engine generates both; never hand-draw them. Bullets are small esmeralda arrows.
- **Logo** only from the kit files via `<div data-logo="h">` (horizontal, cover) or `data-logo="v"` (vertical, closing); the engine swaps the light/dark version with the theme (a MutationObserver on `data-theme`). Never recolor, stretch or redraw it.
- Portuguese, half relaxed half professional ("a gente" → "você"); Brazilian number format (`94,7%`, `R$ 120 mil`, `6,2 h`); every metric with its baseline; every problem/market number with a source in `.src`. No emoji.

## 1. Gather inputs (one AskUserQuestion if anything is missing)

- Hackathon name, challenge/track, date, and the **official pitch rules**: pitch length, separate demo time, Q&A, judging criteria, required sections, submission format.
- What the solution is and the source material (repo, notebook, results, dataset, challenge PDF).
- Team members: names, roles, contacts for the cover and closing slide.
- Which demos must be live and what kind (section 4). For AI demos: a real trained model to embed (ONNX, exported predictions) or simulated? For hardware: real or simulation only.
- **Hosting and domain: always ask with AskUserQuestion, even if nothing else is missing. Never assume a host or domain.** The project runs on AWS and its domain may still be undecided. Offer: AWS, alongside the project's deployment; Vercel on `<slug>.vercel.app`; a domain the user names; or no hosting yet, opened locally. If the user doesn't know the domain, build the deck without one and leave it as an open item in the README.

## 2. Time budget (pitch-length)

- Every slide carries `data-min` in fractions of a minute: cover/agenda 0.25, divider 0.1, common slide 0.4–0.75, live demo 1–2, Q&A 0.
- Sum to the official pitch time (leave ~10% slack). Print the table slide → minutes → planned start and show it to the presenter.
- Default structure (map it to the judging criteria): cover → agenda → problem in one number → solution → how it works (pipeline) → **live demo** → results vs baseline → honest comparison (incl. when NOT to use ours) → next steps / feasibility → synthesis (4 takeaways tied to moments) → team + Q&A.
- Slide text is short; talking points go in `data-notes`.
- HUD pace tolerance is **max(5 s, 5% of total)** — keep it.

## 3. Architecture (copy `template/`, keep the engine intact)

- `1280×720` `#stage` scaled to fit, fixed `#hud` bar (`--hud` verde-escuro in both themes).
- Slides: `<section class="slide" data-min data-title data-notes>`; special classes `cover`, `divider`, `closing`.
- `<body data-team data-event data-topic>` feeds the injected footer on every slide except cover, dividers and the last.
- Hooks `hooks[idx('#canvasId')] = {enter, leave, redraw, keyframes}`; `redraw` runs on theme change so canvases re-read CSS variables.
- **Sandbox-safe**: `history.replaceState`, `location.hash`, fullscreen and `window.print` are wrapped in try/catch with a `flash()` message — previews in sandboxed iframes block them, and an uncaught throw in `go()` kills navigation.
- Keys: ←/→/Space/PageUp/PageDown/Home/End, click progress segments; **T** timer; **R R** reset; **N** notes; **D** theme; **F** fullscreen; **P/PDF** export; **?** shortcuts; **Esc**. Ignore deck keys in inputs; blur sliders on `pointerup`.
- Clock `mm:ss / total`, pace "no ritmo / X atrasado / X adiantado", per-slide budget bar that turns red when overrun.

### PDF export with keyframes (already in the template)

- Static slides → one page; each demo → one page per keyframe (`{label, apply, wait}`), tagged "estado k de n · label" (`.sim-tag.print-tag`, top 18px / right 72px).
- `apply` uses the UI's own setters; keyframes must be deterministic (reset + seeded `mulberry32`).
- Export forces light, repaints logos, restores on `afterprint`. `window.__deckExport` is exposed for Playwright.
- WebGL canvases need `preserveDrawingBuffer: true`. Chrome/Edge honor `@page {size:1280px 720px}`.

### Shared classes

- Type/layout: `.eb`, `.t` (40px 800), `.big` (800 uppercase), `.kicker`, `.lead`, `ul.pts` (esmeralda arrow bullets), `.card`, `.card.hi`, `.bloco`, `.row`, `.col`, `.g2/.g3/.g4`, `.fill`, `.eq`, `.frac`, `.src`, `.ac`, `.bad`, `.muted`.
- Pitch blocks: `.pipe > .st(.on) + .ar` (pipeline with arrow connectors), `.metric` (`.v`, `.bar > i` ours + `u` baseline, `.lg`), `table.cmp` (`tr.us` = our row in `--profundo`), `.team` cards.
- Controls: `.ctl`, `.seg` (`aria-pressed`, active = esmeralda), `.checks`, `.btn.pri` / `.btn.ghost`, `.ro` / `.ro.main`, `.msg` (teaching message, `--alerta` inset rule).
- `.sim-tag` on every demo — `simulação`, `dados reais`, `amostra`, `agregado`, `protótipo`, `modelo treinado`.
- Charts: `--serie-1..4`; hit = `--serie-1`, error = `--alerta`, missed = dashed `--alerta`.
- Accessibility: 2px `--verde` focus ring, `aria-label` on every canvas.

## 4. Demos

| Kind | Example | Core |
|---|---|---|
| **Model in action** | anomaly threshold, classifier on a sample input, forecast vs actual | Real exported predictions or a small in-browser model; threshold/input controls; live precision/recall |
| **Physical or engineering simulation** | motor vibration, structural load, control loop | Explicit model with real parameters |
| **Algorithm visualization** | routing, scheduling, graph search | Step-by-step state machine; play/step/speed/reset |
| **Data exploration** | the challenge dataset, before/after | Precomputed data + renderer sized to it |
| **Impact calculator** | cost saved per month | Controls mapped to a visible change |

Rules: canvas 2D (HiDPI, dpr ≤ 2) or inline SVG, WebGL only when needed; vendor every library inline or in the folder (no CDN at the venue). **Every control changes the picture.** Separate computed values from illustration and label honestly. Seeded RNG, reset button, keyframes defined while building. Show the "wrong" choice with a `.msg`. Verify numbers outside the browser (see `template/demo_check.py`) and write expected values in `data-notes`. Results slides use the team's real evaluation; mark placeholders until replaced. Large graphs/datasets: process offline, ship binary typed arrays or aggregated views instead of JSON, load lazily on `enter`, keep layout off the main thread, and state on the slide the real size and what is shown.

## 5. Verify

- Playwright (Chromium preinstalled; never `playwright install`): 1280×766, screenshot `#stage` for every slide in **both themes**, check console errors and overflow.
- Also load the deck with `page.setContent(html)` (no folder next to it) and with `history.replaceState`/`print` stubbed to throw: logos and fonts must still show, navigation must still work.
- Drive each demo through its keyframes; PDF via `__deckExport()` + `emulateMedia('print')` + `page.pdf({width:'1280px',height:'720px',printBackground:true})`; page count = static slides + keyframes; look at each keyframe page.
- Confirm the `data-min` sum vs the official time, contrast in both themes, Portuguese spelling.

## 6. Deliverables

1. **Deck folder** in the project, at `front/pitch/deck/` unless the user names another place: `index.html`, `assets/`, `fonts/`, `vercel.json`, `README.md` with deploy steps for the chosen host. For Vercel: `npm i -g vercel` → `vercel login` → `vercel --prod` → optional `vercel domains add <domain>`, and keep `vercel.json`. For AWS or no hosting: drop `vercel.json`, and for AWS document how the static files get served. If a deploy can't be done from here, say so, and remind the user to redeploy after changes. No zip unless asked.
2. **Preview** as a claude.ai Artifact when the user wants to see it right away (everything already inline).
3. **PDF for submission/judges** from the same keyframes.
4. Offer in one line: a rehearsal script (who says what, timings, demo protocol, likely judge questions) and a backup slide if the demo fails.

## 7. Talking points

- 3–5 short lines per slide, one on-screen action, one hook into the next; split by presenter if several speak.
- Demos: say what will happen before clicking, list expected values, add 2–3 likely judge questions with answers.
- Flag unverified claims (market size, cost, "used by X") and propose safer wording.