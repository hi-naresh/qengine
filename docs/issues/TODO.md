# Future TODO

## Live Trading CFD Improvements

### P1: Ticket Recovery on Startup
- Hydrate `Position._tickets` from broker's existing positions on session start
- Use OANDA `/v3/accounts/{id}/openTrades` endpoint to get individual trades
- Map OANDA trade IDs to internal CFDTicket objects
- File: `qengine/modes/live_mode.py` (init section ~line 91)

### P1: Ticket Persistence
- Persist tickets to DB (or Redis) so they survive process crashes
- On restart, reload tickets from DB before syncing with broker
- Files: `qengine/models/Position.py`, new repository for tickets

### P2: OANDA /trades Endpoint Integration
- Add `get_open_trades()` to OandaDriver returning per-trade data (id, instrument, units, openTime, price)
- Map internal ticket IDs ↔ OANDA trade IDs on order fill
- Store `exchange_trade_id` on CFDTicket
- Use for precise per-trade close instead of aggregate reduce_only
- File: `qengine/live_drivers/OANDA/OandaDriver.py`

### P2: Position Sync with Ticket Awareness
- `_sync_positions_with_broker()` should rebuild ticket structure from broker `/trades`
- Detect orphaned broker trades (no matching internal ticket)
- Detect stale internal tickets (no matching broker trade)
- File: `qengine/modes/live_mode.py` (~line 288)

### P3: Reduce Order Sync Latency
- Current: 3s poll interval for order fills
- Consider OANDA streaming `/transactions` endpoint for real-time fill detection
- Would improve hedge timing in fast markets
- File: `qengine/modes/live_mode.py` (line 397)

### P3: Per-Instrument Margin from Broker
- Currently uses global `default_leverage` for all symbols
- OANDA has per-instrument margin rates (EUR/USD 30:1, exotic pairs lower)
- Fetch from OANDA `/instruments` endpoint during `_fetch_precisions()`
- File: `qengine/live_drivers/OANDA/OandaDriver.py`
