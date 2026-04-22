# 08 — Broker Mechanics

## Question
How do real broker rules change the strategy's behavior relative to theory? Does OANDA's integer lot rounding cause systematic under/over-hedging? Does NAV-based margin closeout trigger earlier than equity-based models assume?

## Approach
Generalized broker model first, then instantiate with OANDA's actual parameters. Compare against backtester behavior to verify the model.

## Scripts
| Script | Question |
|--------|----------|
| `01_lot_rounding.py` | OANDA rounds to integer units: does the rounding bias compound across levels? |
| `02_margin_closeout_model.py` | NAV-based vs equity-based closeout: exact difference in real bust timing |
| `03_oanda_vs_generalized.py` | Generalized broker model with parameterized margin/lot rules → OANDA as instance |

## Key Output
- Lot rounding bias: expected under/over-hedge per level as function of position size
- NAV closeout model: formula for actual closeout trigger vs theoretical margin level
- Generalized broker model that can be parameterized for any CFD broker

## Findings
<!-- Filled in as research progresses -->
