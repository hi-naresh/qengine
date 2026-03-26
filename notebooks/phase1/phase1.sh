#!/usr/bin/env bash
# Run all phase1 research scripts and save results to notebooks/phase1/results/
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Users/naresh/miniconda3/bin/python3"

echo "=== Phase 1 Research Scripts ==="
echo "Results will be saved to: $SCRIPT_DIR/results/"
echo ""

mkdir -p "$SCRIPT_DIR/results"

SCRIPTS=(
    02_atr_distance_sweep.py
    03_cooldown_session.py
    04_monte_carlo.py
    05_full_cycle_simulation.py
    06_cycle_pnl_analysis.py
    07_bust_anatomy.py
    08_abort_and_sizing.py
    09_monte_carlo_corrected.py
    10_capital_scaling_risk.py
    11_tail_risk_deep_dive.py
    12_risk_equations.py
    13_blind_backtest.py
    14_loss_paths.py
)

FAILED=()

for script in "${SCRIPTS[@]}"; do
    echo "--- Running $script ---"
    if "$PYTHON" "$SCRIPT_DIR/$script"; then
        echo "--- $script OK ---"
    else
        echo "--- $script FAILED ---"
        FAILED+=("$script")
    fi
    echo ""
done

echo "=== Done ==="
echo "Results in: $SCRIPT_DIR/results/"
ls -1 "$SCRIPT_DIR/results/"*.png 2>/dev/null | wc -l | xargs -I{} echo "{} PNG files generated"

if [ ${#FAILED[@]} -gt 0 ]; then
    echo ""
    echo "FAILED scripts:"
    for f in "${FAILED[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
