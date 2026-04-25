# IslandPilot — Cloud Training on Google Cloud Platform

Everything runs from **your local terminal**. You never need to open the GCP console for the actual training.

---

## Iteration scope

The pipeline has been developed in two iterations. **Iteration 1 is the achievement reported in the dissertation** and is the focus of this guide. Iteration 2 is implemented in code as a design endpoint identified by Iteration 1's results; the valuable insights from Iteration 1 motivate further exploration of Iteration 2 in the conference-paper extension of this work.

| | **Iteration 1 (cloud-trained, reported)** | Iteration 2 (design endpoint, future work) |
|---|---|---|
| Status | Trained, evaluated, reported in §6 | Implementation complete in source; full-scale evaluation deferred |
| Tunable groups evolved | 3 (General, Grid/Hedge, Take Profit) + 5 pipeline-level genes | 7 (adds Entry Signal, Filters, Risk Management, Position Management) |
| Genes per genome | 20 | 57 |
| Categorical-gene resolution | Not required (no categoricals in the genome) | Required (`_resolve_categorical_genes`) |
| CFD margin-bust state-leakage fix | Applied at OOS evaluation | Required at training as well |
| Available models | `models/` directory (downloaded post-run) | None |

The 20-gene Iteration 1 model is the one whose OOS results (PF 0.877, −0.83% net, 84.73% → 0.75% max DD) are reported in the dissertation. Iteration 2 widens the search space to include per-regime entry-signal, risk-management, and position-management genes. The dissertation's Iteration 1 evidence — particularly the 113-fold drawdown reduction with no directional alpha — motivates investigating Iteration 2's wider search space as part of the conference-paper extension this work is heading towards.

---

## What you get (Iteration 1, the cloud-trained model)

| Config | Time (20 gen × 63 islands × 10 pop = 12,600 evals) |
|--------|----------------------------------------------------|
| MacBook (local, sequential) | ~10+ days |
| GCP `c2-standard-60` (spot) | **~10 h 33 min** |

Measured wall-clock on `c2-standard-60` for the primary cloud run (2026-04-23 → 2026-04-24): **10 h 33 min** for the full 20-generation × 63-island × 10-individual configuration on the 2022–2024 EUR-USD 5m training window. Per-generation throughput averages 1,888 s (≈ 31.5 min) including sibling-migration steps.

Iteration 2 has a wider search space (57 genes versus 20) and is identified as future work for the conference-paper extension; full-scale evaluation is deferred pending further heavy computation.

> **Quota note**: new GCP accounts may have C2 CPU quota below 60. If `c2-standard-60` is unavailable, request a quota increase via IAM & Admin → Quotas → filter "C2 CPUs" in `europe-west2`. Iteration 1 was executed on `c2-standard-60` (London, spot).

---

## Part 1 — One-time local setup

### 1. Install the gcloud CLI

```bash
brew install --cask google-cloud-sdk
gcloud --version
```

### 2. Log in

```bash
gcloud auth login
# Opens a browser — sign in with the GCP account configured for compute
```

### 3. Set your project

```bash
gcloud projects list
gcloud config set project YOUR_PROJECT_ID
```

### 4. Enable Compute Engine API

```bash
gcloud services enable compute.googleapis.com
```

### 5. Set default zone (London)

```bash
gcloud config set compute/zone europe-west2-c
```

> **Zone availability**: `europe-west2-c` is the verified zone for `c2-standard-60` spot capacity. `europe-west2-b` was tried during development but reported `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`. If `-c` ever returns the same error, try `europe-west2-a`.

---

## Part 2 — Export candles (one time, ~30 sec)

The cloud VM has no PostgreSQL. Export once from local:

```bash
cd /Users/naresh/Documents/Research/qengine
conda activate qengine
python export_candles.py
# Output: candles_oanda_eurusd_1m_2022_2024.npy  (~53 MB)
```

---

## Part 3 — Every training run

### Step 1 — Create the VM

Run as a **single line** (zsh treats line breaks as separate commands):

```bash
gcloud compute instances create islandpilot-train --machine-type=c2-standard-60 --zone=europe-west2-c --provisioning-model=SPOT --instance-termination-action=STOP --image-family=debian-12 --image-project=debian-cloud --boot-disk-size=30GB --boot-disk-type=pd-ssd
```

Check it started (wait ~60 seconds):
```bash
gcloud compute instances list
# STATUS should be RUNNING
```

> The reference Iteration 1 run used `c2-standard-60`. Smaller machine types are not recommended for the 12,600-evaluation configuration; smaller spot quotas should be raised before launching.

### Step 2 — Pack and upload the repo

Pack locally (exclude node_modules and .git to keep it small):
```bash
cd /Users/naresh/Documents/Research
tar -czf /tmp/qengine.tar.gz --exclude='qengine/node_modules' --exclude='qengine/.git' qengine/
```

Upload via IAP tunnel (always use `--tunnel-through-iap` — port 22 is blocked on new GCP projects):
```bash
gcloud compute scp --tunnel-through-iap /tmp/qengine.tar.gz "islandpilot-train:/home/naresh/qengine.tar.gz" --zone=europe-west2-c
gcloud compute scp --tunnel-through-iap /Users/naresh/Documents/Research/qengine/candles_oanda_eurusd_1m_2022_2024.npy "islandpilot-train:/home/naresh/candles_oanda_eurusd_1m_2022_2024.npy" --zone=europe-west2-c
```

Extract on the VM:
```bash
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap -- "cd ~ && tar -xzf qengine.tar.gz && mv candles_oanda_eurusd_1m_2022_2024.npy ~/qengine/"
```

> **Two-username gotcha**: `gcloud compute ssh` connects as user `naresh` (home: `/home/naresh/`). The GCP browser SSH connects as a different user (e.g. `nareshjhawar9`). Always work from the gcloud terminal and keep working files in the user's actual home.

### Step 3 — Set up Python environment (once per fresh VM)

```bash
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap
```

Inside the VM:
```bash
sudo apt-get update -q && sudo apt-get install -y python3 python3.11-venv tmux
python3 -m venv ~/venv
~/venv/bin/pip install numpy scikit-learn fastapi sqlalchemy pydantic requests arrow pandas psycopg2-binary peewee --quiet
nproc   # should print 60 on c2-standard-60
```

Type `exit` to leave the SSH session.

### Step 4 — Start training

SSH in and launch inside tmux so it survives connection drops:

```bash
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap
```

Inside the VM:
```bash
tmux new -s train
cd ~/qengine && QENGINE_TRAINING_MODE=1 ~/venv/bin/python3 -u -m pipelines._shared.IslandPilot.train --generations 20 --pop-size 10 --workers 0 --candles-file candles_oanda_eurusd_1m_2022_2024.npy
```

Detach (keeps running after you close SSH): **Ctrl+B then D**

Expected output (Iteration 1 reference run, 2026-04-23 → 2026-04-24):
```
[train]   Workers: 60 / 60 CPUs
[train] Loaded 1,106,233 1m candles from file.
[train] Resampled to 221,246 5m candles for feature computation.
[train] Computing 30 features on 221246 candles...
[train] Selected 3 features: ['natr_14_tf12', 'natr_14_tf48', 'natr_50']
[train] MI selected only 3 features — falling back to all 30 features for stable regimes.
[train] RegimeTree fitted: 10 macro clusters, 63 leaves.
[train] Built gene bounds from strategy: 20 genes.
[train] Active islands (with window ≥ 30 days): 0 / 63
[train] NOTE: 63/63 islands have no dedicated window — will evolve on full training period
[train] Generation 1/20...
[train]   Mean best fitness: 55.964 (min=51.529, max=58.977) [1843s]
[train] Generation 2/20...
[train]   Mean best fitness: 56.507 (min=51.974, max=59.077) [1917s]
...
[train] Generation 20/20...
[train]   Mean best fitness: 58.867 (min=58.090, max=59.200) [1880s]
[train] Training complete. Total elapsed: 10.55h (37966s)
```

Two log lines are worth understanding for the dissertation results:

- **`Built gene bounds from strategy: 20 genes`** — Iteration 1 evolved 20 genes (5 pipeline-level + 15 strategy-level across General, Grid/Hedge, Take Profit). Iteration 2 widens this to 57 genes by adding the Entry Signal, Risk Management, and Position Management groups; that change is in the source tree but has not been executed at scale.
- **`Active islands (with window ≥ 30 days): 0 / 63`** — every island evolved on the full 2022–2024 training window rather than on a regime-specific contiguous activation window. The 30-day-window filter rejected all 63 leaves on this training distribution; this is a known limitation of the Iteration 1 setup. Iteration 2 retains the same fitness-isolation mechanism in code; whether per-regime windows materialise depends on the regime distribution of the (future) re-fit feature matrix.

### Step 5 — Download results when done

The training writes to `/home/<vm-user>/qengine/pipelines/_shared/IslandPilot/models/`. Because the gcloud SSH user (`naresh`) and the working user on the VM may differ, stage the files into `/home/naresh/` first, then SCP them down.

From your **local terminal**:

```bash
# Stage cloud models in naresh's home with naresh-readable ownership
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap -- "\
  sudo rm -rf /home/naresh/models_out && \
  sudo mkdir -p /home/naresh/models_out && \
  sudo cp /home/nareshjhawar9/qengine/pipelines/_shared/IslandPilot/models/regime_tree.pkl \
          /home/nareshjhawar9/qengine/pipelines/_shared/IslandPilot/models/island_evolver.json \
          /home/nareshjhawar9/qengine/pipelines/_shared/IslandPilot/models/island_genomes.json \
          /home/nareshjhawar9/qengine/pipelines/_shared/IslandPilot/models/leaf_date_ranges.json \
          /home/naresh/models_out/ && \
  sudo chown -R naresh:naresh /home/naresh/models_out"

# Download all four artefacts
gcloud compute scp --tunnel-through-iap \
  "islandpilot-train:/home/naresh/models_out/regime_tree.pkl" \
  "islandpilot-train:/home/naresh/models_out/island_evolver.json" \
  "islandpilot-train:/home/naresh/models_out/island_genomes.json" \
  "islandpilot-train:/home/naresh/models_out/leaf_date_ranges.json" \
  /Users/naresh/Documents/Research/qengine/pipelines/_shared/IslandPilot/models/ \
  --zone=europe-west2-c
```

If the VM was created and used as the same user (no two-username problem), the simpler form works:

```bash
gcloud compute scp --tunnel-through-iap --recurse \
  "islandpilot-train:~/qengine/pipelines/_shared/IslandPilot/models/" \
  /Users/naresh/Documents/Research/qengine/pipelines/_shared/IslandPilot/ \
  --zone=europe-west2-c
```

### Step 6 — Delete the VM (stop paying)

```bash
gcloud compute instances delete islandpilot-train --zone=europe-west2-c
```

> Spot VMs still charge for disk storage when stopped. Always delete when done.

---

## Updating a single local file on the VM

When you change a file locally and need to push it to the running VM:

```bash
# Step 1: upload to naresh's home (gcloud SSH user)
gcloud compute scp --tunnel-through-iap /Users/naresh/Documents/Research/qengine/PATH/TO/FILE.py \
  "islandpilot-train:/home/naresh/FILE.py" --zone=europe-west2-c

# Step 2: copy into the working repo (use sudo if the working user differs)
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap -- \
  "sudo cp /home/naresh/FILE.py ~nareshjhawar9/qengine/PATH/TO/FILE.py"
```

---

## Cheat sheet — monitor from local terminal

```bash
# Check VM status
gcloud compute instances list

# Re-attach to tmux session
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap
tmux attach -t train          # detach again with Ctrl+B then D

# See last 100 lines of training output without attaching to tmux
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap -- \
  "tmux capture-pane -pt train -S -100"

# Check CPU usage
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap -- \
  "top -bn1 | head -5"

# Check disk space
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap -- \
  "df -h"

# Stop VM (pause billing, keeps disk — can restart later)
gcloud compute instances stop islandpilot-train --zone=europe-west2-c

# Restart a stopped VM
gcloud compute instances start islandpilot-train --zone=europe-west2-c
```

### Cheat sheet — from inside the VM

If you are already SSH'd into the VM, gcloud commands won't authenticate (the VM has limited service-account scopes). Use plain shell commands instead:

```bash
# Is training running?
pgrep -af IslandPilot.train || echo 'NOT RUNNING'

# See last 40 lines of tmux scrollback
tmux capture-pane -pt train -S -40

# List tmux sessions
tmux ls

# Attach (live view; detach with Ctrl+B D)
tmux attach -t train

# CPU / memory snapshot
top -bn1 | head -5
```

---

## Troubleshooting

**"Quota exceeded"** — Request a quota increase via GCP Console → IAM & Admin → Quotas → filter "C2 CPUs" in `europe-west2`. Iteration 1 used `c2-standard-60` and is the configuration documented in this guide.

**SSH/SCP times out** — Always use `--tunnel-through-iap`. Port 22 is blocked on new GCP projects. If it still times out, the VM may still be booting — wait 60s and retry.

**`ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`** — c2-standard-60 spot capacity in your zone is full. Try `europe-west2-c` first; fall back to `-a` or `-b`.

**"externally-managed-environment"** — Debian 12 blocks `pip` on the system Python. Use the venv: `~/venv/bin/pip` and `~/venv/bin/python3`.

**"No module named X"** — Install missing dep: `~/venv/bin/pip install X --quiet`

**"Spot VM got preempted"** — GCP reclaimed the instance. Re-create it (Step 1) and re-upload. Training restarts from scratch (no checkpoint). Rare but possible at the spot price point.

**Two usernames on the VM** — `gcloud compute ssh` connects as `naresh` (home: `/home/naresh/`). The GCP browser SSH and the apt-installed Python venv may live under a different user (e.g. `nareshjhawar9`). When in doubt: `whoami`, then `ls /home/`. Use `sudo cp` to bridge files between the two homes; staging through `/home/naresh/` is the safest pattern for SCP.

**`QENGINE_TRAINING_MODE` must be set** — Without it, qengine tries to connect to PostgreSQL and Redis on startup (which don't exist on the VM) and crashes. Always prefix the training command with `QENGINE_TRAINING_MODE=1`. Section 4.2 of the paper documents the underlying isolation logic.

**"index 13 is out of bounds" during fitness eval** — Indicator called with insufficient candle history. The pipeline's filter and signal guards (Martingale `_filters_pass`, `_get_signal`) gate on `len(self.candles)` < 200. If you see this trace, ensure `warm_up_candles=210` is set in the backtest config and that the engine's warmup phase has elapsed before the strategy fires.

---

## Reference run summary (Iteration 1, the reported result)

| Item | Value |
|------|-------|
| Machine | Google Cloud `c2-standard-60` (spot) |
| vCPUs | 60 |
| Region | `europe-west2-c` (London) |
| Training data | 1,106,233 1m candles (2022-01-01 to 2024-12-31) |
| Resampled | 221,246 5m candles (after weekend-gap removal: 220,608 clean rows) |
| Regime tree | 10 macro clusters × 63 leaves |
| Tunable groups (evolved) | 3 (General, Grid/Hedge, Take Profit) + 5 pipeline-level genes |
| Genes per genome | 20 |
| Backtests | 20 gen × 63 islands × 10 pop = 12,600 evaluations |
| Active islands w/ contiguous 30-day window | 0 / 63 (all evolved on full training window) |
| Wall-clock (measured) | 10 h 33 min (37,966 s) |
| Per-generation mean | 1,888 s (≈ 31.5 min) |

> **Iteration 2 outlook**: the corrected pipeline widens the search space to 7 tunable groups and 57 genes per genome. Iteration 1's evidence — particularly the 113-fold drawdown reduction without directional alpha — motivates further investigation of Iteration 2's wider search space, which is identified as the next direction for the conference-paper extension this research is heading towards.
