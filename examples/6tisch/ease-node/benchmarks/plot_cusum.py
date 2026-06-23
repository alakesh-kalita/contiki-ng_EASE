#!/usr/bin/env python3
"""
Plot CUSUM estimation vs actual traffic for root's children.
Style: transmitter (actual D_t) vs receiver (CUSUM prediction) over time,
with threshold lines for burst detection.

Usage:
    python3 plot_cusum.py /path/to/COOJA.testlog
    python3 plot_cusum.py  # auto-finds latest /tmp/ease_*/COOJA.testlog
"""

import sys
import os
import re
import glob
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib as mpl
from collections import defaultdict

# Global font size increase
mpl.rcParams.update({
    'font.size': 14,
    'axes.titlesize': 16,
    'axes.labelsize': 15,
    'xtick.labelsize': 13,
    'ytick.labelsize': 13,
    'legend.fontsize': 12,
    'legend.title_fontsize': 12,
})


def find_latest_log():
    logs = glob.glob('/tmp/ease_*/COOJA.testlog')
    if not logs:
        print("No COOJA.testlog found in /tmp/ease_*/")
        sys.exit(1)
    return max(logs, key=os.path.getmtime)


def parse_cusum(logfile, parent_id=1):
    """Extract CUSUM data for children of a given parent."""
    children = defaultdict(list)
    re_cusum = re.compile(
        r'CUSUM (\S+): D_t=(\d+), adj=(\d+), cells=(\d+), pred=(\d+)')

    with open(logfile, 'r', errors='replace') as f:
        for line in f:
            parts = line.strip().split(None, 2)
            if len(parts) < 3:
                continue
            try:
                ts_us = int(parts[0])
                nid = int(parts[1])
            except ValueError:
                continue
            if nid != parent_id:
                continue
            m = re_cusum.search(parts[2])
            if m:
                child_addr = m.group(1)
                child_id = int(child_addr.split('.')[0], 16)
                if child_id == 0 or child_id == parent_id:
                    continue
                children[child_id].append({
                    'time_min': ts_us / 60e6,
                    'D_t': int(m.group(2)),
                    'adj': int(m.group(3)),
                    'cells': int(m.group(4)),
                    'pred': int(m.group(5)),
                })
    return children


def plot_cusum(children, output_path, parent_id=1, max_children=3):
    """Plot actual vs estimated in A3/ALICE style."""
    ranked = sorted(children.keys(),
                    key=lambda c: sum(d['D_t'] for d in children[c]),
                    reverse=True)
    selected = ranked[:max_children]

    if not selected:
        print("No CUSUM data found for parent {}".format(parent_id))
        return

    fig, axes = plt.subplots(len(selected), 1,
                              figsize=(14, 3.5 * len(selected)),
                              sharex=True)
    if len(selected) == 1:
        axes = [axes]

    for idx, child_id in enumerate(selected):
        ax = axes[idx]
        data = children[child_id]
        times = np.array([d['time_min'] for d in data])
        actual = np.array([d['D_t'] for d in data])
        predicted = np.array([d['pred'] for d in data])
        cells = np.array([d['cells'] for d in data])

        # Compute EWMA of actual for smoother transmitter line
        alpha = 0.15
        actual_ewma = np.zeros(len(actual), dtype=float)
        if len(actual) > 0:
            actual_ewma[0] = actual[0]
            for i in range(1, len(actual)):
                actual_ewma[i] = (1 - alpha) * actual_ewma[i-1] + alpha * actual[i]

        # Compute EWMA of predicted for smoother receiver line
        pred_ewma = np.zeros(len(predicted), dtype=float)
        if len(predicted) > 0:
            pred_ewma[0] = predicted[0]
            for i in range(1, len(predicted)):
                pred_ewma[i] = (1 - alpha) * pred_ewma[i-1] + alpha * predicted[i]

        # Normalize to rate (0-1 scale like the reference plot)
        max_val = max(max(actual_ewma) if len(actual_ewma) else 1,
                      max(pred_ewma) if len(pred_ewma) else 1, 1)
        norm = max_val if max_val > 0 else 1

        # Plot transmitter (actual) and receiver (estimated)
        ax.plot(times, actual_ewma / norm, color='#3333CC', linewidth=1.2,
                label='tx attempt rate (actual D_t)', zorder=3)
        ax.plot(times, pred_ewma / norm, color='#CC3333', linewidth=1.2,
                label='estimated tx attempt rate (CUSUM)', zorder=3)

        # Threshold lines
        # H_high = burst detection threshold (normalized)
        # H_low = cell decrease threshold
        h_high = 0.75
        h_high_prime = 0.65
        h_low = 0.36
        h_low_prime = 0.29

        ax.axhline(y=h_high, color='#6666CC', linestyle='--', linewidth=0.8,
                   alpha=0.7)
        ax.axhline(y=h_high_prime, color='#6666CC', linestyle='--',
                   linewidth=0.8, alpha=0.5)
        ax.axhline(y=h_low, color='#CC6666', linestyle='--', linewidth=0.8,
                   alpha=0.7)
        ax.axhline(y=h_low_prime, color='#CC6666', linestyle='--',
                   linewidth=0.8, alpha=0.5)

        # Threshold labels on right side
        ax.text(times[-1] + 0.3, h_high, r'$\tau_H$', fontsize=13,
                color='#6666CC', va='center')
        ax.text(times[-1] + 0.3, h_high_prime, r"$\tau'_H$", fontsize=13,
                color='#6666CC', va='center')
        ax.text(times[-1] + 0.3, h_low, r'$\tau_L$', fontsize=13,
                color='#CC6666', va='center')
        ax.text(times[-1] + 0.3, h_low_prime, r"$\tau'_L$", fontsize=13,
                color='#CC6666', va='center')

        ax.set_ylabel('tx attempt rate')
        ax.set_ylim(-0.05, 1.15)
        ax.set_xlim(times[0] - 0.5, times[-1] + 1.5)

        # Title as subtitle
        ax.set_title('Link (Node {}, Node {})'.format(parent_id, child_id),
                     style='italic')

        # Legend
        if idx == 0:
            legend = ax.legend(loc='upper left', ncol=2,
                              framealpha=0.9,
                              title='transmitter                    receiver')

        ax.grid(True, alpha=0.2)

        # Stats annotation
        avg_dt = sum(actual) / len(actual) if actual.size else 0
        avg_pred = sum(predicted) / len(predicted) if predicted.size else 0
        ax.text(0.98, 0.95,
                'Avg D_t={:.2f}, Avg pred={:.2f}'.format(avg_dt, avg_pred),
                transform=ax.transAxes, fontsize=12,
                ha='right', va='top',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='wheat',
                          alpha=0.5))

    axes[-1].set_xlabel('time [min]')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    # Also save PDF
    pdf_path = output_path.replace('.png', '.pdf')
    plt.savefig(pdf_path, bbox_inches='tight')
    plt.close()
    print('Saved: {}'.format(output_path))
    print('Saved: {}'.format(pdf_path))


def main():
    if len(sys.argv) > 1:
        logfile = sys.argv[1]
    else:
        logfile = find_latest_log()

    print('Log: {}'.format(logfile))

    children = parse_cusum(logfile, parent_id=1)
    print('Found {} children of root with CUSUM data'.format(len(children)))

    if not children:
        print('No CUSUM data. Make sure EASE is running with CUSUM logging.')
        return

    for cid in sorted(children.keys()):
        data = children[cid]
        total = sum(d['D_t'] for d in data)
        print('  Child {}: {} slotframes, {} total pkts'.format(
              cid, len(data), total))

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, 'evaluation_results')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'cusum_estimation.png')
    plot_cusum(children, output_path, parent_id=1, max_children=3)


if __name__ == '__main__':
    main()
