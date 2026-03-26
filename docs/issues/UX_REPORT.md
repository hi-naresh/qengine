# QEngine Frontend — Complete UX Audit

**Date:** 2026-03-26
**Scope:** All views, components, layout, design system

---

## P0: Critical (Breaks mobile usability)

| # | Issue | Where | Fix |
|---|-------|-------|-----|
| 1 | **Tables not mobile-responsive** — 7-12 column tables force horizontal scroll on every data view | Backtest (trades, sessions, costs, exposure), LiveTrade (positions, orders, closed trades, history), Optimization (best trials, history), MonteCarlo, Strategies, Tools, ImportData | Convert to card layout on mobile (`md:hidden` cards + `hidden md:table-cell` table), or add `overflow-x-auto` + `min-w-[Xpx]` + sticky first column |
| 2 | **Touch targets < 44px** — close buttons (×), tab buttons, filter chips, icon-only actions are 20-30px | All workspace tabs, all modals, Issues action buttons, chart toolbar, log filters, timeframe selectors | Add `min-w-[44px] min-h-[44px]` or increase padding to `p-3` on mobile |
| 3 | **Hover-only interactions invisible on touch** — delete buttons, tab close buttons use `opacity-0 group-hover:opacity-100` | ImportData delete, workspace tab close buttons, session card actions | Use `opacity-100 sm:opacity-0 sm:group-hover:opacity-100` |
| 4 | **`text-[10px]` below readable minimum** — used for metric labels, table headers, filter buttons, chart labels | LiveTrade (lines 122-165), Backtest (line 286), Optimization (lines 191, 339), MonteCarlo, Tools | Replace all `text-[10px]` with `text-xs` (12px) minimum |

---

## P1: High (Significantly hurts UX)

| # | Issue | Where | Fix |
|---|-------|-------|-----|
| 5 | **No button `:active` states on mobile** — no tap feedback on any button | `style.css` btn classes | Add `.btn-primary:active { @apply bg-brand-700 scale-[0.97]; }` etc. |
| 6 | **Metrics grids cramped on mobile** — `grid-cols-2` with long labels on 320px screens | Backtest, Optimization, LiveTrade, Strategies (performance metrics grids) | Use `grid-cols-1 xs:grid-cols-2 md:grid-cols-4` |
| 7 | **Modal close/dismiss missing keyboard support** — no Escape key handler, no focus trap | All modals (Backtest strategy editor, Optimization candidate, LiveTrade start session, Issues, Settings) | Add `@keydown.esc="close"` and focus management |
| 8 | **Chart expanded mode ignores safe areas** — full-screen chart covers notch/home indicator | TradeChart.vue expanded mode | Add `env(safe-area-inset-*)` to expanded positioning |
| 9 | **Tab overflow has no scroll indicators** — users don't know more tabs exist | Workspace tabs in Backtest, Optimization, MonteCarlo, Strategies; result tabs; detail tabs in LiveTrade | Add fade gradient on edges or scroll arrow indicators |
| 10 | **No max content width on desktop** — content stretches infinitely on ultrawide monitors | App.vue main content area | Add `max-w-[1600px] mx-auto` inside `<main>` |
| 11 | **Tablet navigation gap** — sidebar hidden below `lg:` (1024px), bottom nav shows below `lg:` — works but some tablet users may prefer sidebar | App.vue, Sidebar.vue, BottomNav.vue | Consider showing condensed sidebar on `md:` breakpoint |
| 12 | **Fixed-height scroll areas too short on landscape mobile** — `max-h-[400px]`, `max-h-[500px]` hard-coded | LiveTrade logs, trades; Optimization modals; MonteCarlo sessions | Use `max-h-[60vh]` instead of fixed pixel values |
| 13 | **Input font-size responsive breakpoint too early** — drops to 14px at `sm:` (640px), triggers iOS zoom on iPads | `style.css` line 117 | Change from `min-width: 640px` to `min-width: 768px` |

---

## P2: Medium (Polish & consistency)

| # | Issue | Where | Fix |
|---|-------|-------|-----|
| 14 | **Badge contrast fails WCAG AA** — 15% opacity bg + 400-weight text ≈ 2.5:1 ratio | `style.css` badge classes | Increase to `/20` bg, `text-*-300`, add `font-semibold` |
| 15 | **No loading skeletons** — blank areas or "Loading..." text during async loads | Dashboard, LiveTrade, all session loads | Add skeleton pulse placeholders matching content layout |
| 16 | **Missing ARIA labels on icon-only buttons** — screen readers say "button" with no context | Issues edit/delete, chart toolbar, workspace close, copy DNA, session actions | Add `aria-label="Edit issue"` etc. |
| 17 | **No confirmation for destructive live trading actions** — Stop/Remove session in LiveTrade has no "are you sure?" | LiveTrade stop/remove session buttons | Add confirmation modal for live account actions |
| 18 | **Empty states could be more helpful** — generic "No data" messages without guidance | Backtest costs, LiveTrade positions/orders, Dashboard broker empty | Add icons, descriptive text, and action buttons |
| 19 | **Color-only status indicators** — red/green dots without text alternatives | Dashboard running tasks, LiveTrade session status | Add `<span class="sr-only">Running</span>` |
| 20 | **Glass blur values inconsistent** — sidebar 24px, cards 20px, sheets 32px | Sidebar, BottomNav, style.css card class | Standardize with CSS variables `--glass-blur`, `--glass-blur-strong` |
| 21 | **Settings tabs text wrapping** — "Cost & Randomness" wraps mid-word on mobile | Settings.vue tab buttons | Add `whitespace-nowrap` or abbreviate to "Cost Model" |
| 22 | **Checkbox options wrapping** — long descriptions ("logs every step, slower") wrap awkwardly | Backtest.vue checkbox section | Stack description below checkbox label on mobile |
| 23 | **Login form missing `autocomplete` attributes** — password managers can't auto-fill | Login.vue password input | Add `autocomplete="current-password"` |
| 24 | **Toast position can overlap bottom nav** — `bottom-20` may not clear floating nav with `mx-6 mb-4` | ToastContainer.vue | Increase to `bottom-24` on mobile |
| 25 | **Firefox scrollbar unstyled** — only webkit scrollbar CSS provided | `style.css` desktop scrollbar section | Add `scrollbar-width: thin; scrollbar-color:` for Firefox |

---

## P3: Low (Nice-to-have polish)

| # | Issue | Where | Fix |
|---|-------|-------|-----|
| 26 | **No `prefers-reduced-motion` support** — animations play regardless of OS setting | All transitions and animations | Wrap in `@media (prefers-reduced-motion: reduce) { transition: none; }` |
| 27 | **Focus-visible vs focus** — mouse clicks show focus rings unnecessarily | `style.css` input focus | Change `:focus` to `:focus-visible` |
| 28 | **Z-index scale undocumented** — z-40, z-50, z-[100] scattered | Multiple components | Define named z-index scale in tailwind config |
| 29 | **Router `isActive` uses `startsWith`** — `/live` would match `/live-stream` if route existed | Sidebar.vue, BottomNav.vue | Check `path === to || path.startsWith(to + '/')` |
| 30 | **Dashboard activity time format locale-dependent** — `toLocaleString()` can be very long | Dashboard.vue | Use short format options `{ month: 'short', day: 'numeric', hour: '2-digit' }` |
| 31 | **No data export from tables** — users can't copy/export trade history, session data | All table views | Add CSV export button to table headers |

---

## Per-View Detail

### Dashboard.vue
- Running tasks cards: `truncate` without `max-w-*` can fail on narrow screens — add `flex-1 min-w-0`
- Activity grid cards: `p-3` touch targets only ~60px, increase to `p-4 sm:p-3`
- Market status grid: jumps from 1 to 3 columns — add `sm:grid-cols-2` intermediate
- Broker empty state: generic message, add icon and helpful guidance
- Refresh button: `text-xs` is small — increase to `text-sm`, add `aria-label`

### Login.vue
- `max-w-sm` + `px-4` leaves only 304px on 320px devices — consider `max-w-md px-6 sm:max-w-sm`
- Logo `w-16 h-16` too large on small phones — make responsive `w-12 h-12 sm:w-16 sm:h-16`
- Button height ~40px below 44px minimum — add `min-h-[48px]`
- No loading spinner in button during auth
- Missing `autocomplete="current-password"` on password input
- No error recovery: password not cleared/refocused on failure

### Backtest.vue
- **Exposure table**: 11 columns, no `overflow-x-auto` wrapper — add wrapper + `min-w-[800px]`
- **Sessions table**: nested table inside collapsible — add responsive wrapper
- **Trades table**: 12+ columns — add overflow container + hide optional columns on mobile
- **Costs table**: 10 columns — add overflow wrapper
- **Metrics grids** (lines 366, 377, 387, 397, 410, 501, 712, 753): all `grid-cols-2 md:grid-cols-4` — add `grid-cols-1 xs:grid-cols-2`
- **Strategy editor modal**: appears inline, not proper modal on mobile — wrap in full-screen modal
- **Chart heights** (lines 483, 487, 491): fixed 220px/180px — make `h-[180px] sm:h-[220px]`
- **Hyperparameters**: `w-28 truncate` cuts off names — remove fixed width, allow wrapping
- **Routes config** (line 47): `grid-cols-1 sm:grid-cols-3` makes form very long on mobile
- **Close buttons** (×): text characters without proper 44px touch targets throughout
- **Exposure size toggle** (lines 292-298): `text-[10px]` buttons too small to tap
- Add sticky table headers for long scrolling tables

### LiveTrade.vue
- **All tables** (positions, orders, closed trades, history): 7-12 columns, need card layout on mobile
- **Account overview grids** (lines 120, 142): 5 items in `grid-cols-2` creates odd 2-2-1 layout
- **Detail tabs**: `text-xs` too small for tap targets — increase padding
- **Log filter buttons**: `text-[10px]` extremely small — increase to `text-xs`
- **Modal form** (lines 23-37): needs `grid-cols-1 sm:grid-cols-2` for mobile
- **Pulsing status**: `animate-pulse` on both dot and text is distracting — only animate dot
- **Polling interval**: 2s may be aggressive on mobile networks — consider 5s on mobile
- **No confirmation** for Stop/Remove session actions on live accounts
- **Session tabs**: no limit on open tabs, no badge for updated data
- **Ticket/Session ID display**: `slice(0, 8)` — add copy-to-clipboard button
- **Fixed scroll heights**: `max-h-[400px]`/`max-h-[500px]` — use `max-h-[60vh]`

### Optimization.vue
- **Best trials table** (line 235): horizontal scroll without indicators
- **History table** (line 320): many columns, cramped on mobile
- **Modal tables** (lines 556, 662): same overflow issues
- **Chart** (lines 201-225): labels at `text-[10px]` unreadable on small screens
- **Config panel disappears during run** — keep visible but disable inputs, or add summary card
- **Circular progress** (lines 410-421): no ARIA `aria-valuenow`/`aria-valuemin`/`aria-valuemax`
- **Cancel vs Terminate**: inconsistent terminology — use "Stop Optimization" consistently
- **"Copy DNA"**: tech jargon — rename to "Copy Parameters" or add tooltip
- **Session dates** at `text-[10px]` — illegible, stack vertically on mobile
- **Empty states**: missing for charts and best trials before data arrives
- **Error traceback**: `text-[10px]` in `max-h-[200px]` — increase font and height, add Copy button

### MonteCarlo.vue
- **Workspace tabs**: same overflow issues as other views
- **Table** (lines 218-239): "Original", "Worst 5%", "Median", "Best 5%" columns wide — card layout on mobile
- **SVG chart**: axis labels may overlap on small screens — responsive font sizes
- **Session history table** (lines 352-391): needs card layout on mobile
- **Circular progress**: `w-32 h-32` may be too large on small landscape — use `w-24 h-24 sm:w-32 sm:h-32`
- **Config panel hides during run**: jarring layout shift

### Strategies.vue
- **Editor tabs**: can get very wide with multiple strategies — limit visible + "+N" indicator
- **Action buttons** (Playground, Edit, Delete): small text-only touch targets — add padding
- **Hyperparameter inputs**: complex nested layout wraps poorly — stack on mobile
- **Inline editor**: `min-h-[500px]` takes entire screen — reduce on mobile or use modal
- **Trades table**: 7 columns, needs overflow handling
- **Result tabs**: count labels "(25)" add unnecessary width on mobile

### Tools.vue
- **Instruments table**: 7 columns with `min-w-[600px]` — hide Base/Quote on mobile
- **Pip calculator result grid**: `grid-cols-2 sm:grid-cols-4` cramped — add `grid-cols-1` for xs
- **Trading calculator results**: `text-[10px]` too small — use `text-xs`
- **Detail modal**: `grid-cols-2` tight on 320px — add `grid-cols-1 xs:grid-cols-2`

### LLMStudio.vue
- **Two-column layout**: code output below form on mobile — consider showing code first with `order-first`
- **Textarea height**: `min-h-[100px]` small — increase to `min-h-[120px]` on mobile
- **Form grid**: `sm:grid-cols-3` cramped on tablets — add `sm:grid-cols-2 md:grid-cols-3`
- **Code preview**: `text-xs` hard to read on mobile — consider `text-sm`
- **Disabled button**: no tooltip explaining why disabled

### Issues.vue
- **Issue title**: `truncate` may hide important info — use `line-clamp-2` instead
- **Action buttons**: `w-3.5 h-3.5` icons too small — increase with proper tap area
- **Quick status buttons**: `text-[10px]` — increase to `text-xs` with `min-h-[36px]`

### Settings.vue
- **Tabs**: "Cost & Randomness" wraps mid-word — add `whitespace-nowrap`
- **Webhook URLs**: can overflow card — add `truncate` or `break-all`
- **Helper text**: `text-xs text-surface-600` very low contrast — use `text-surface-500`
- **Backtest settings**: two-column grids tight on 320px — add xs breakpoint
- **Password input**: no show/hide toggle
- **System info values**: long OS version wraps awkwardly — add `break-words`

### Brokers.vue
- **Card info grid**: `grid-cols-3` cramped on narrow cards — use `grid-cols-2 sm:grid-cols-3`
- **Environment status rows**: long status text may overflow — add `flex-wrap` or stack
- **Modal connection details**: three info pieces wrap awkwardly — stack on mobile

### ImportData.vue
- **Existing data table**: 7 columns with `min-w-[600px]` — card layout on mobile
- **Delete button**: `opacity-0 group-hover:opacity-100` invisible on touch — always show on mobile
- **Timeframes badges**: too many badges clutter row — show first 3-4 + "+N more"

---

## Design System Issues

### Spacing Scale
- Mix of `gap-1`, `gap-2`, `gap-3`, `gap-6` without consistent system
- Card padding not responsive — should be `p-3 md:p-4 lg:p-6`
- Button group spacing inconsistent

### Typography Scale
- `text-[10px]`, `text-xs`, `text-sm`, `text-base`, `text-2xl` without clear hierarchy rules
- **Minimum readable size should be `text-xs` (12px)**
- Consider defining semantic scale: caption (12px), body-sm (14px), body (16px), heading-sm (18px), heading (20px), display (24px)

### Color Contrast
- `text-surface-500` on dark backgrounds may fail WCAG AA (4.5:1 required)
- `text-surface-600` definitely fails — use for decorative only, not informational text
- Badge colors at 15% opacity too faint

### Z-Index Scale
- z-40: Sidebar, BottomNav sheets
- z-50: Chart expanded, modals, BottomNav bar
- z-[100]: Toast
- Should be documented and named in tailwind config

### Glass Effect Standardization
- Define `--glass-blur: 24px` and `--glass-blur-strong: 32px` as CSS variables
- Currently sidebar, nav, sheets, cards all use different values

---

## Recommended Implementation Order

### Phase 1 — Mobile Critical (P0)
Items 1-4. Makes the app actually usable on phones.
- Table responsive layouts (card views on mobile)
- Touch target fixes (44px minimum)
- Hover-only interaction fixes for touch
- Minimum font size enforcement (12px)

### Phase 2 — Touch & Feel (P1 subset)
Items 5, 6, 9, 12, 13. Makes it feel like a native app.
- Button active states
- Metrics grid responsive fixes
- Tab scroll indicators
- Viewport-relative scroll heights
- Input font-size breakpoint fix

### Phase 3 — Desktop & Accessibility (P1+P2)
Items 7, 8, 10, 14, 16, 19. Proper desktop experience + a11y compliance.
- Modal keyboard support
- Chart safe area handling
- Max content width
- Badge contrast fixes
- ARIA labels
- Status indicator text alternatives

### Phase 4 — Polish (P2+P3)
Everything else. Final refinements.
- Loading skeletons
- Empty state improvements
- Firefox scrollbar
- Reduced motion support
- Focus-visible fixes
- Data export
