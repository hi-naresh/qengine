# IslandPilot — Cloud Training on Google Cloud Platform

Everything runs from **your local terminal**. You never need to open the GCP console for the actual training.

---

## What you get

| Config | Cores | Time (20 gen × 56 islands × 10 pop) | Cost |
|--------|-------|--------------------------------------|------|
| MacBook (local, sequential) | 1 | ~10 days | — |
| GCP c2-standard-8 (spot) | 8 | ~13 hrs | ~£0.35 |
| GCP c2-standard-60 (spot) | 60 | **~40 min** | **~£0.50** |

£222 credit covers ~440 full training runs on the 60-core machine.

> **Current quota**: new GCP accounts are limited to 12 CPUs globally — use `c2-standard-8`. Request a quota increase for `c2-standard-60`.

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
# Opens a browser — sign in with the GCP account that has the £222 credit
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

> After a quota increase, swap `c2-standard-8` → `c2-standard-60` (~40 min, £0.50).

### Step 2 — Pack and upload the repo

Pack locally (exclude node_modules and .git to keep it small):
```bash
cd /Users/naresh/Documents/Research
tar -czf /tmp/qengine.tar.gz --exclude='qengine/node_modules' --exclude='qengine/.git' qengine/

tmux new -s train                                                                                                      
cd ~/qengine && QENGINE_TRAINING_MODE=1 ~/venv/bin/python3 -m pipelines._shared.IslandPilot.train --generations 20 --pop-size 10 --workers 0 --candles-file candles_oanda_eurusd_1m_2022_2024.npy  
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

### Step 3 — Set up Python environment (once per fresh VM)

```bash
gcloud compute ssh islandpilot-train --zone=europe-west2-c --tunnel-through-iap                                                                                                                                              
```

Inside the VM:
```bash
sudo apt-get update -q && sudo apt-get install -y python3 python3.11-venv && python3 -m venv ~/venv && ~/venv/bin/pip install numpy scikit-learn fastapi sqlalchemy pydantic requests arrow pandas psycopg2-binary peewee --quiet && nproc   
sudo apt-get install -y tmux
ls /home/naresh/                                                                                                       
cp -r /home/naresh/qengine ~/qengine                                                                                         
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
cd ~/qengine && QENGINE_TRAINING_MODE=1 ~/venv/bin/python3 -m pipelines._shared.IslandPilot.train --generations 20 --pop-size 10 --workers 0 --candles-file candles_oanda_eurusd_1m_2022_2024.npy
```

Detach (keeps running after you close SSH): **Ctrl+B then D**

Expected output per generation:
```
[train] Generation 1/20...
[train]   Mean best fitness: 54.3 (min=49.1, max=61.2) [118s]
[train] Generation 2/20...
```

### Step 5 — Download results when done

From your **local terminal**:

```bash
gcloud compute scp --tunnel-through-iap --recurse "islandpilot-train:~/qengine/pipelines/_shared/IslandPilot/models/" /Users/naresh/Documents/Research/qengine/pipelines/_shared/IslandPilot/ --zone=europe-west2-c
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
gcloud compute scp --tunnel-through-iap /Users/naresh/Documents/Research/qengine/PATH/TO/FILE.py "islandpilot-train:/home/naresh/FILE.py" --zone=europe-west2-b

# Step 2: move it into the repo
gcloud compute ssh islandpilot-train --zone=europe-west2-b --tunnel-through-iap -- "cp /home/naresh/FILE.py ~/qengine/PATH/TO/FILE.py"
```

---

## Cheat sheet — monitor from local terminal
From inside the VM, just run these directly:

cd ~/qengine && QENGINE_TRAINING_MODE=1 ~/venv/bin/python3 -u -m pipelines._shared.IslandPilot.train --generations 20 --pop-size 10 --workers 0 --candles-file candles_oanda_eurusd_1m_2022_2024.npy

# Is training running?
pgrep -af IslandPilot.train || echo 'NOT RUNNING'

# See the last 40 lines of tmux output
tmux capture-pane -pt train -S -40

# List tmux sessions
tmux ls

# Attach to the training session (live view)
tmux attach -t train
# detach without killing: Ctrl+B then D

# CPU usage
top -bn1 | head -5

```bash
# Check VM status
gcloud compute instances list


# Re-attach to tmux session
gcloud compute ssh islandpilot-train --zone=europe-west2-b --tunnel-through-iap
tmux attach -t train

# See last 100 lines of training output without SSHing in
gcloud compute ssh islandpilot-train --zone=europe-west2-b --tunnel-through-iap -- "tmux capture-pane -pt train -S -100"

# Check CPU usage
gcloud compute ssh islandpilot-train --zone=europe-west2-b --tunnel-through-iap -- "top -bn1 | head -5"

# Check disk space
gcloud compute ssh islandpilot-train --zone=europe-west2-b --tunnel-through-iap -- "df -h"

# Stop VM (pause billing, keeps disk — can restart later)
gcloud compute instances stop islandpilot-train --zone=europe-west2-b

# Restart a stopped VM
gcloud compute instances start islandpilot-train --zone=europe-west2-b
```

---

## Troubleshooting

**"Quota exceeded"** — Use `c2-standard-8` (8 CPUs). Request increase: GCP Console → IAM & Admin → Quotas → filter "C2 CPUs" in europe-west2.

**SSH/SCP times out** — Always use `--tunnel-through-iap`. Port 22 is blocked on new GCP projects. If it still times out, the VM may still be booting — wait 60s and retry.

**"externally-managed-environment"** — Debian 12 blocks `pip` on the system Python. Use the venv: `~/venv/bin/pip` and `~/venv/bin/python3`.

**"No module named X"** — Install missing dep: `~/venv/bin/pip install X --quiet`

**"Spot VM got preempted"** — GCP reclaimed the instance. Re-create it (`Step 1`) and re-upload. Training restarts from scratch (no checkpoint). Rare but possible.

**Two usernames on the VM** — `gcloud compute ssh` connects as `naresh` (home: `/home/naresh/`). The GCP browser SSH connects as a different user. Always work from the gcloud terminal and keep files in `/home/naresh/`.

**`QENGINE_TRAINING_MODE` must be set** — Without it, qengine tries to connect to PostgreSQL and Redis on startup (which don't exist on the VM) and crashes. Always prefix the training command with `QENGINE_TRAINING_MODE=1`.

---

## Cost estimate for paper

| Item | Value |
|------|-------|
| Machine | Google Cloud c2-standard-60 (spot) |
| vCPUs | 60 |
| Region | europe-west2 (London) |
| Training data | 1,106,233 1m candles (2022-01-01 to 2024-12-31) |
| Backtests | 20 gen × 56 islands × 10 pop = 11,200 evaluations |
| Expected wall time | ~40 minutes |
| Compute cost | ~£0.50 |
