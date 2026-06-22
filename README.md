# EASE: Energy-Aware Autonomous Scheduling for 6TiSCH

EASE is an autonomous TSCH scheduling scheme for IEEE 802.15.4e networks that combines receiver-based shared cells for bootstrapping with CUSUM-predicted dedicated cells for data traffic, constrained by a game-theoretic RDC budget. It is implemented as a module for Contiki-NG, integrating with the Orchestra scheduling framework.

---

## Table of Contents

1. [File Structure](#file-structure)
2. [How EASE Works](#how-ease-works)
3. [Configuration Parameters](#configuration-parameters)
4. [Building and Running](#building-and-running)
5. [Performance Evaluation](#performance-evaluation)

---

## File Structure

### EASE Module — `os/services/ease/`

| File | Lines | Description |
|------|-------|-------------|
| **`ease.h`** | ~75 | Public API. Defines `struct ease_child_state` (CUSUM state, quota, tokens, cell count per child). Declares all EASE functions. |
| **`ease.c`** | ~200 | Core algorithms. **CUSUM predictor** (Eq. 2-5): runs at each slotframe boundary, estimates traffic demand per child. Utilization-aware — adjusts D_t upward when cells are saturated. **Game theory** (Eq. 6-16): bisection on λ to find Nash Equilibrium allocations within RDC budget B = δ×SF. Caps CUSUM predictions to fair share. **Token bucket** (Eq. 17): initializes tokens per child each slotframe. **NACK**: withholds ACK when tokens=0. **Self-CUSUM**: child-side predictor mirrors parent's estimation for symmetric cell allocation. |
| **`ease-conf.h`** | ~170 | All configurable parameters with `#ifdef` guards for override. Zone sizes, CUSUM thresholds, game theory bounds, hash function, channel seed. |
| **`ease-rule-dedicated-cell.c`** | ~250 | Orchestra scheduling rule. **Receiver-based shared cell**: `hash(EUI64(P))` — permanent RX cell, created at init, never removed until parent change. Children create matching TX\|SHARED cell. **Pair-based dedicated cells**: `hash(263×EUI64(P) + EUI64(C) + i)` — added incrementally by `ease_update_dedicated_cells()` when CUSUM predictions increase. Never removed except on parent change or child removal. **select_packet**: routes to shared cell by default; after fairness triggers, routes to dedicated cell. |
| **`ease-rule-shared-cell.c`** | ~60 | Placeholder for Orchestra framework compatibility. The actual shared cell is handled within the dedicated cell rule (both zones in same slotframe). |
| **`module-macros.h`** | ~5 | Sets `BUILD_WITH_EASE=1` compile flag. |
| **`Makefile.ease`** | ~1 | Adds `-DBUILD_WITH_EASE=1` to CFLAGS. |

### Modified Contiki-NG Core Files

| File | What Changed | Why |
|------|-------------|-----|
| **`os/services/orchestra/orchestra.c`** | Added `#if BUILD_WITH_EASE` blocks in `orchestra_packet_received()` and `orchestra_packet_sent()` | Calls `ease_check_slotframe_boundary()` on every packet event for CUSUM timing. Calls `ease_notify_rx(src)` on received frames (excluding parent and self) to track child traffic. Calls `ease_notify_tx()` and `ease_notify_shared_tx_success()` on successful TX to parent for self-CUSUM and fairness tracking. Detects `parent_knows_us` on first successful TX to parent. |
| **`os/services/orchestra/orchestra.h`** | Added `extern struct orchestra_rule ease_shared_cell, ease_dedicated_cell;` | Declares EASE Orchestra rules so they can be referenced in `ORCHESTRA_CONF_RULES`. |
| **`os/net/mac/tsch/tsch-slot-operation.c`** | Added optional `TSCH_CALLBACK_SLOTFRAME_BOUNDARY` hook (guarded by `#ifdef`) | Enables precise slotframe-boundary detection for ASFN-based scheduling (currently unused — EASE uses fixed positions). |
| **`os/net/mac/tsch/tsch.c`** | Added optional callback processing in `tsch_pending_events_process` (guarded by `#ifdef`) | Processes slotframe boundary events in main thread context (currently unused). |
| **`os/net/routing/rpl-classic/rpl-mrhof.c`** | Added `#ifndef` guard around `PARENT_SWITCH_THRESHOLD` | Allows override from project-conf.h for RPL stability tuning (optional). |

### Example Application — `examples/6tisch/ease-node/`

| File | Description |
|------|-------------|
| **`node.c`** | UDP application. Node 1 = DAG root (server), nodes 2-25 = senders (clients). Logs `PERF-TX` on send, `PERF-RX` on receive (with timestamps for latency calculation). Logs `ENERGEST` every 60s for RDC measurement. Packet rate configurable via `EASE_PACKETS_PER_MIN`. EASE headers guarded with `#if BUILD_WITH_EASE`. |
| **`project-conf.h`** | Complete configuration: EASE parameters (SF=101, budget=20%, CUSUM thresholds), Orchestra rules (EASE dedicated + shared + default), TSCH callbacks (DO_NACK, packet ready, time source), RPL storing mode, energest enabled, logging levels. |
| **`Makefile`** | Includes both Orchestra and EASE modules. Sets TSCH MAC and RPL Classic routing. |
| **`ease-25node.csc`** | Cooja simulation file. 25 ContikiMotes, 5×5 grid, 30m spacing. UDGM radio: 50m TX range, 100m interference, perfect links. Node 1 at (0,0) = DAG root. |
| **`ease-cooja.csc`** | Original 5-node test simulation for quick debugging. |
| **`run_evaluation.py`** | Automated evaluation script. Supports 3 schemes: `ease`, `orchestra-sb`, `orchestra-rb`. Iterates over slotframe lengths [67, 101, 131, 163] × packet rates [4, 6, 8, 10]. For each config: writes scheme-specific project-conf.h and Makefile, cleans build, runs Cooja headless (30-min simulation), parses COOJA.testlog (10-min warmup), computes PDR/RDC/latency/channel-utilization, outputs CSV. Restores original files on exit. |
| **`plot_results.py`** | Generates comparison plots from evaluation CSV. Per-rate 2×2 grids (all metrics vs SF), per-SF 2×2 grids (all metrics vs rate), individual metric plots. Handles both old (EASE-only) and new (multi-scheme) CSV formats. |
| **`plot_cusum.py`** | Plots CUSUM estimation vs actual traffic for root's children. Shows D_t (actual packets), c_{t+1} (CUSUM prediction), and allocated cells over time. Finds the most active children automatically. |

---

## How EASE Works

### Slotframe Structure

```
|<-------- Zone 1 (shared) -------->|G|<-------- Zone 2 (dedicated) -------->|
  slot 0        ...        slot SFs-1   slot SFs+1       ...        slot SF-1

  SFs = SF/2 (e.g., 50 for SF=101)
  SFx = SF - SFs - 1 (e.g., 50)
  Guard slot at position SFs
```

### Data Flow per Slotframe

```
Slotframe N:
  1. Child has packet → sends on SHARED CELL (Zone 2, receiver-based)
     - Timeslot: hash(EUI64(parent))
     - Multiple children contend via CSMA/CA
     - Parent always listening (permanent RX cell)

  2. If successful → ease_notify_shared_tx_success() sets fairness flag

Slotframe N+1:
  3. Fairness active → child SKIPS shared cell
  4. Child sends on DEDICATED CELL (Zone 2, pair-based)
     - Timeslot: hash(263 × EUI64(P) + EUI64(C) + i)
     - Both sides compute independently — same result
     - No contention (dedicated to this pair)

  5. CUSUM at parent: observes D_t, predicts c_{t+1}
     - If prediction increases → adds more dedicated cells incrementally
     - If saturated (D_t ≥ cells) → adjusts demand upward

  6. Game theory: caps prediction within RDC budget
     - quota = NE allocation from bisection
     - if predicted > quota → predicted = quota

  7. Token bucket: tokens initialized per child
     - Decremented on each received packet
     - tokens = 1 → EACK (informing quato exhaution)
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Receiver-based shared cell `hash(P)` | Parent always has RX cell — no bootstrapping delay. Unlike pair-based `hash(P,C)`, parent doesn't need to know the child first. |
| Asymmetric hash `263×P + C` | Prevents collision between pairs with same address sum (e.g., nodes 4→9 and 7→6 both sum to 13). Factor 263 (prime > 256) ensures unique hash inputs. |
| Incremental cell addition | `ease_update_dedicated_cells()` only adds new cells when CUSUM prediction increases. Never removes existing cells. Full rebuild only on parent change or child removal. |
| Game theory as CAP, not FLOOR | CUSUM drives allocation. Game theory only restricts when prediction exceeds the fair share. At low traffic, CUSUM prediction (1 cell) < quota (4-5 cells) → no restriction. |

---

## Configuration Parameters

### `ease-conf.h`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `EASE_UNICAST_PERIOD` | 101 | Slotframe length (timeslots) |
| `EASE_SHARED_ZONE_SIZE` | SF/2 | Zone 1 size |
| `EASE_DEDICATED_ZONE_SIZE` | SF - SFs - 1 | Zone 2 size |
| `EASE_DEDICATED_ZONE_START` | SFs + 1 | Zone 2 first slot |
| `EASE_RDC_BUDGET_PCT` | 20 | RDC budget δ (%) |
| `EASE_CUSUM_THRESHOLD` | 500 | Burst detection H (×100) |
| `EASE_CUSUM_RHO` | 80 | EWMA coefficient ρ (×100) |
| `EASE_MAX_CHILDREN` | 10 | Max children per parent |
| `EASE_MAX_CELLS_PER_CHILD` | 10 | Max dedicated cells per child |
| `EASE_DEFAULT_WEIGHT` | 1 | Child priority weight |
| `EASE_MIN_CELLS_PER_CHILD` | 0 | Minimum cells per child |
| `EASE_BISECTION_ITERATIONS` | 16 | NE solver iterations |
| `EASE_LAMBDA_SCALE` | 1000 | Fixed-point scale for λ |
| `EASE_ALPHA_UP` | 1 | Hash multiplier (upward) |
| `EASE_ALPHA_DOWN` | 2 | Hash multiplier (downward) |
| `EASE_NUM_CHANNELS` | 16 | Available channels |
| `EASE_CHANNEL_HASH_SEED` | 0x9E3779B9 | Decorrelates channel from timeslot |
| `EASE_WITH_GAME_THEORY` | 1 | Enable game theory |

### `project-conf.h` (example)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `EASE_CONF_UNICAST_PERIOD` | 101 | Override slotframe length |
| `EASE_PACKETS_PER_MIN` | 4 | Application packet rate |
| `EASE_CONF_MAX_CHILDREN` | 25 | For 25-node network |
| `ORCHESTRA_CONF_RULES` | `{EB, dedicated, shared, common}` | Rule priority order |
| `TSCH_SCHEDULE_CONF_MAX_LINKS` | 128 | Accommodate dedicated cells |

---

## Building and Running

### Prerequisites

- Contiki-NG (this repo)
- Cooja simulator (included in `tools/cooja/`)
- Java 21+ (`brew install openjdk@21` on macOS)
- Python 3.8+ with `matplotlib`, `numpy`

### Build

```bash
cd examples/6tisch/ease-node
make TARGET=cooja
```

### Run in Cooja GUI

```bash
cd tools/cooja
./gradlew run
# File → Open → examples/6tisch/ease-node/ease-25node.csc
# Start simulation
```

### Run Headless (single config)

```bash
cd tools/cooja
./gradlew run --args='--no-gui --contiki=../.. \
  --logdir=/tmp/ease_test \
  ../../examples/6tisch/ease-node/ease-25node.csc'
```

Note: The base CSC file does not include a ScriptRunner for headless mode. Use `run_evaluation.py` which adds it automatically.

---

## Performance Evaluation

### Automated Evaluation

```bash
cd examples/6tisch/ease-node

# Run all schemes × all configs (48 simulations, ~80 min)
python3 run_evaluation.py

# Run specific scheme(s)
python3 run_evaluation.py --scheme ease
python3 run_evaluation.py --scheme ease orchestra-sb

# Run specific configs
python3 run_evaluation.py --scheme ease --sf 101 --rate 4

# Parse existing logs without re-running
python3 run_evaluation.py --parse-only
```

### Supported Schemes

| Scheme | Flag | Orchestra Rule | Description |
|--------|------|---------------|-------------|
| `ease` | `--scheme ease` | `ease_dedicated_cell` + `ease_shared_cell` | EASE with CUSUM + game theory |
| `orchestra-sb` | `--scheme orchestra-sb` | `unicast_per_neighbor_rpl_storing` | Orchestra sender-based |
| `orchestra-rb` | `--scheme orchestra-rb` | `unicast_per_neighbor_rpl_ns` | Orchestra receiver-based |

### Plot Results

```bash
# Comparison plots (after evaluation)
python3 plot_results.py

# CUSUM estimation accuracy
python3 plot_cusum.py evaluation_results/ease_sf101_rate4/COOJA.testlog
```

### Output Files

All results saved to `evaluation_results/`:

```
evaluation_results/
├── evaluation_results.csv              # Metrics for all configs
├── comparison_vs_sf_rate4.png          # 2×2 plots: all metrics vs SF
├── comparison_vs_rate_sf101.png        # 2×2 plots: all metrics vs rate
├── pdr_vs_sf_rate4.png                 # Individual: PDR vs SF
├── avg_rdc_vs_rate_sf101.png           # Individual: RDC vs rate
├── cusum_estimation.png                # CUSUM prediction accuracy
├── ease_sf101_rate4/COOJA.testlog      # Raw simulation log
├── orchestra-sb_sf101_rate4/COOJA.testlog
└── ...
```

### Metrics Computed

| Metric | Formula | Source |
|--------|---------|-------|
| **PDR (%)** | RX packets / TX packets × 100 | `PERF-TX` and `PERF-RX` log lines |
| **RDC (%)** | (radio TX + radio listen) / total time × 100 | `ENERGEST` log lines |
| **E2E Latency (ms)** | rx_ticks - tx_ticks | Timestamp in `PERF-RX` vs `PERF-TX` |
| **Channel Util. (%)** | aggregate TX time / total time × 100 | `ENERGEST` TX ticks |

---

### Debugging

```bash
# Check CUSUM predictions
grep 'CUSUM' COOJA.testlog | grep ' 1 ' | tail -10

# Check game theory
grep 'Game NE' COOJA.testlog | tail -5

# Check RPL loops
python3 -c "
import re
p = {}
with open('COOJA.testlog') as f:
    for l in f:
        m = re.search(r'uc-\d+-\d+ tx LL-([0-9a-f]+)->LL-([0-9a-f]+)', l)
        if m: p[int(m.group(1),16)] = int(m.group(2),16)
for s in sorted(p):
    path = [s]; c = s
    for _ in range(10):
        pp = p.get(c)
        if pp is None or pp == 1: break
        if pp in path: print(f'LOOP: {path}'); break
        path.append(pp); c = pp
"

# Check dedicated cell additions
grep 'Ded\[' COOJA.testlog | tail -10
```

