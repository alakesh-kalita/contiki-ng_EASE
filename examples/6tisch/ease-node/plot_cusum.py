#!/usr/bin/env python3
"""
Plot CUSUM estimation vs actual traffic for root's children.

Reads COOJA.testlog, extracts D_t (actual) and predicted (CUSUM estimate)
for 2-3 children of the root, plots them side by side.

Usage:
    python3 plot_cusum.py /path/to/COOJA.testlog
    python3 plot_cusum.py  # uses most recent /tmp/ease_*/COOJA.testlog
"""

import sys
import os
import re
import glob
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict

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
                    'time_s': ts_us / 1e6,
                    'D_t': int(m.group(2)),
                    'adj': int(m.group(3)),
                    'cells': int(m.group(4)),
                    'pred': int(m.group(5)),
                })
    return children

def plot_cusum(children, output_path, parent_id=1, max_children=3):
    """Plot actual vs estimated for top children."""
    # Pick children with most traffic
    ranked = sorted(children.keys(),
                    key=lambda c: sum(d['D_t'] for d in children[c]),
                    reverse=True)
    selected = ranked[:max_children]

    if not selected:
        print("No CUSUM data found for parent {}".format(parent_id))
        return

    fig, axes = plt.subplots(len(selected), 1,
                              figsize=(12, 4 * len(selected)),
                              sharex=True)
    if len(selected) == 1:
        axes = [axes]

    fig.suptitle('CUSUM: Actual Traffic vs Estimated (Parent = Node {})'
                 .format(parent_id),
                 fontsize=14, fontweight='bold')

    for idx, child_id in enumerate(selected):
        ax = axes[idx]
        data = children[child_id]
        times = [d['time_s'] for d in data]
        actual = [d['D_t'] for d in data]
        predicted = [d['pred'] for d in data]
        cells = [d['cells'] for d in data]

        ax.step(times, actual, where='post', linewidth=1.2,
                color='#1f77b4', alpha=0.7, label='Actual (D_t)')
        ax.step(times, predicted, where='post', linewidth=2,
                color='#ff7f0e', label='CUSUM Estimated (c_{t+1})')
        ax.step(times, cells, where='post', linewidth=1.5,
                color='#2ca02c', linestyle='--', alpha=0.6,
                label='Allocated cells')

        ax.set_ylabel('Packets / Cells', fontsize=11)
        ax.set_title('Child Node {}'.format(child_id), fontsize=12)
        ax.legend(fontsize=9, loc='upper right')
        ax.grid(True, alpha=0.3)
        ax.set_ylim(bottom=-0.2)

        avg_dt = sum(actual) / len(actual) if actual else 0
        avg_pred = sum(predicted) / len(predicted) if predicted else 0
        ax.text(0.02, 0.95,
                'Avg D_t={:.2f}, Avg pred={:.2f}, Samples={}'.format(
                    avg_dt, avg_pred, len(data)),
                transform=ax.transAxes, fontsize=9,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    axes[-1].set_xlabel('Time (seconds)', fontsize=11)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print('Saved: {}'.format(output_path))


def main():
    if len(sys.argv) > 1:
        logfile = sys.argv[1]
    else:
        logfile = find_latest_log()

    print('Log: {}'.format(logfile))

    children = parse_cusum(logfile, parent_id=1)
    print('Found {} children of root with CUSUM data'.format(len(children)))

    if not children:
        print('No CUSUM data. Make sure EASE is running with CUSUM enabled.')
        return

    for cid in sorted(children.keys()):
        data = children[cid]
        total = sum(d['D_t'] for d in data)
        print('  Child {}: {} slotframes, {} total pkts'.format(
              cid, len(data), total))

    output_dir = os.path.dirname(logfile)
    output_path = os.path.join(output_dir, 'cusum_estimation.png')
    plot_cusum(children, output_path, parent_id=1, max_children=3)


if __name__ == '__main__':
    main()
