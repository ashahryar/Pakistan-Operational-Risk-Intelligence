# Dashboard design system (Task 42)

## How it was chosen

`ui-ux-pro-max` was run with `--design-system` for "disaster operational intelligence command center government data platform" (density 8, motion 2, variance 3). It returned style **Minimalism & Swiss** (grid-based, high contrast, functional; "best for enterprise apps, dashboards"), typography **Dashboard Data** (Fira Code for figures, Fira Sans for text), a blue primary with an amber accent, subtle motion, and the avoid-list "ornate design". Domain searches added: choropleth guidance (label regions directly, pair fills with boundaries, provide a sortable region table as a fallback; no colour-only meaning) and the "colour is never the only signal" rule.

Deviation, stated plainly: the skill's default surface is light; PORI keeps a **dark operations-console surface** (the skill lists dark as supported) because every legacy page and chart was already dark. The tokens are the skill's blue/amber family re-derived for dark and verified by `tests/dashboard/test_design_system.py` (every text colour on every surface >= 4.5:1; every status badge text on its tinted fill >= 4.5:1).

## One system, in code

| Concern | Where |
|---|---|
| Colour, type scale, spacing, radius, status semantics | `dashboard/ui/tokens.py` (mirrored as CSS variables in `dashboard/styles/design_system.css`, checked equal by a test) |
| Components: KPI row (`st.metric`), status badge, freshness chip, notice (info / warn / error / unavailable), legend, provenance footer, empty state | `dashboard/ui/components.py` |
| Plotly template `pori` (default), `style_fig`, `map_layout` | `dashboard/ui/charts.py` |
| Risk choropleth (status fill + glyph + label, selected-area outline, no colour bar) | `dashboard/ui/maps.py` |
| Shell: theme injection, grouped sidebar, application bar, page header with freshness chips | `dashboard/ui/shell.py` (`shell.begin()` / `shell.finish()`) |

* **Typography**: Fira Sans (text) and Fira Code (figures); 28 / 22 / 16 / 14 / 12 px scale; one radius (6 px); 4-pt spacing.
* **Status language**: risk statuses (Critical ◆, High ▲, Moderate ◐, Low ●, Insufficient data ○, No signal –, No risk record ·), freshness (Latest available ●, Stale ◐, Source unavailable ✕, No observations ○) and geography evidence each have a glyph **and** a label; colour is an addition, never the signal. The map fills, badges, legend, tables and agent views read the same palette (`STATUS_COLORS` is derived from the tokens).
* **Freshness**: `Latest available · 30 Sep 2026`, `Stale · latest successful snapshot 14 Jul 2026 (85 days old)`, `Source unavailable — latest successful snapshot: 12 Aug 2026`, `No observations available`. Real dates always; computed from `/api/v1/freshness`.
* **Navigation**: Overview (Executive Overview) / National monitoring (NDMA Casualties, NDMA Damage, PMD Weather, PDMA Rainfall, River & Gauge Network) / Operational intelligence (Risk Map) / AI & evidence (Intelligence Workspace, with the modes Agent, Analyze Risk, Ask Reports). Implementation names ("Task 34") are not shown.
* **Accessibility**: visible 2 px focus ring, reduced-motion respected, meaningful labels, glyph + text statuses, charts have captions and a table alternative on the Risk Map (area list) and Rivers (station table with CSV).

## Legacy pages

NDMA Casualties, NDMA Damage, PMD Weather and PDMA Rainfall keep their existing analytics code (about 7,000 lines). They now sit inside the shared shell: their own `--cs-/--im-/--ob-` tokens are remapped to the shared tokens, their duplicate page titles and sidebar brands are hidden, and their charts use the `pori` template. Their inner card headings still carry some emoji and mono-caps styling; a full rewrite of those pages was not part of this task.
