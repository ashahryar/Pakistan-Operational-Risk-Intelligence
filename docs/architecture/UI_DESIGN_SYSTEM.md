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

## Visualization and motion (second Task 42 pass)

Every important chart is a builder in `dashboard/ui/charts.py` with one analytical purpose; tooltips name the entity (never an internal id), the value with its unit, the date and the source.

| Builder | Question it answers | Honesty rule |
|---|---|---|
| `time_series` | How did X change and how complete is the history? | Real date axis; 7d / 30d / 90d / All selectors only for windows the data can fill; optional range slider; unified hover; the latest observation is a marked point; lines are never joined across missing dates and sparse history is stated under the chart |
| `ranked_bar` | Which areas are highest right now? | Names the "as of" date and source in the tooltip |
| `animated_bars` | How did the picture build up report by report? | Starts paused (Play / Pause, never autoplay); value axis fixed so movement means change; frames are real report dates; refused above 60 frames; a category missing from a frame has no bar (never 0) |
| `status_distribution`, `status_timeline` | How many areas per status? How did one area's status change? | Statuses are categories drawn as markers with no connecting line (no trend implied); glyph + label on every bar |
| `coverage_timeline` | Which stations reported over which dates? | A first-to-latest range, labelled as such: not proof of daily reports |

Pages:
* **NDMA Casualties / Damage** (`sections/impact_views.py`): latest cumulative by province, national cumulative trend, "added by each report" increments, and a weekly-checkpoint progression. The cumulative line is the sum of provinces' latest cumulative figures; a province that never reported a measure stays missing; reports are never summed.
* **PDMA Rainfall** (`sections/rainfall_views.py`): highest/median per report (gaps visible), latest-report ranking, intensity bands, station coverage per report, and a Play/Pause progression over the latest 60 report dates. District-list and header "stations" are counted as unresolved.
* **PMD Weather** (`sections/weather_views.py`): comparisons inside the single dated snapshot (temperature by city, temperature vs humidity, day-1 conditions). There is no history, so there is no trend; every chart names the snapshot date.
* **Risk Map**: status distribution for the scope, the selected area's status history, `uirevision` so zoom and pan survive filter changes, and a loading state for the boundary fetch.
* **River & Gauge Network**: reporting period per station, observation days per station, and an interactive station inspector. No level, danger or flood-risk indicator.
* **Evidence** (all three Intelligence modes): an evidence overview table (cited / retrieved, source, document, date, geography, relevance, provenance). Only passages that passed the relevance check appear.

Motion: one 200 ms rise (opacity and 6 px) for notices, chips, badges, KPIs, charts, tables and expanders; nothing loops; `prefers-reduced-motion` turns it off. Plotly figures carry a 250 ms transition setting. Streamlit re-runs the page on a filter change and may replace a chart rather than morph it, so smooth value morphing is not guaranteed; the animations that do run (Play / Pause) are native Plotly frames and only run on request.

## Legacy pages

NDMA Casualties, NDMA Damage, PMD Weather and PDMA Rainfall keep their existing analytics code (about 7,000 lines). They now sit inside the shared shell: their own `--cs-/--im-/--ob-` tokens are remapped to the shared tokens, their duplicate page titles and sidebar brands are hidden, and their charts use the `pori` template. Their inner card headings still carry some emoji and mono-caps styling; a full rewrite of those pages was not part of this task.
