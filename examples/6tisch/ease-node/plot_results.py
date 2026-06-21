#!/usr/bin/env python3
"""
Plot EASE vs Orchestra performance evaluation results.

Reads evaluation_results.csv and generates comparison plots for
PDR, RDC, E2E Latency, and Channel Utilization across schemes.

Usage:
    python3 plot_results.py
    python3 plot_results.py --csv path/to/results.csv
"""

import os
import csv
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(SCRIPT_DIR, 'evaluation_results', 'ease_evaluation_results.csv')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'evaluation_results')

SCHEME_STYLES = {
    'ease':          {'color': '#1f77b4', 'marker': 'o',  'ls': '-',  'label': 'EASE'},
    'orchestra-sb':  {'color': '#ff7f0e', 'marker': 's',  'ls': '--', 'label': 'Orchestra-SB'},
    'orchestra-rb':  {'color': '#2ca02c', 'marker': '^',  'ls': '-.', 'label': 'Orchestra-RB'},
}

METRICS = [
    ('pdr',            'Packet Delivery Ratio',    'PDR (%)'),
    ('avg_rdc',        'Radio Duty Cycle',         'RDC (%)'),
    ('avg_latency_ms', 'End-to-End Latency',       'Latency (ms)'),
    ('chan_util',       'Channel Utilization',      'Channel Util. (%)'),
]


def load_csv(csv_path):
    rows = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'scheme': row.get('scheme', 'ease'),
                'sf_length': int(row['sf_length']),
                'pkt_rate': int(row['pkt_rate']),
                'pdr': float(row['pdr']),
                'avg_rdc': float(row['avg_rdc']),
                'avg_latency_ms': float(row['avg_latency_ms']),
                'chan_util': float(row['chan_util']),
            })
    return rows


def organize(rows):
    """Organize by scheme -> metric -> {x_val: y_val}."""
    by_sf = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    by_rate = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for r in rows:
        scheme = r['scheme']
        sf = r['sf_length']
        rate = r['pkt_rate']
        for key, _, _ in METRICS:
            by_sf[key][scheme][rate][sf] = r[key]
            by_rate[key][scheme][sf][rate] = r[key]
    return by_sf, by_rate


def plot_vs_sf(rows, output_dir):
    """2x2: x-axis = slotframe length, one line per scheme, grouped by rate."""
    by_sf, _ = organize(rows)
    sfs = sorted({r['sf_length'] for r in rows})
    rates = sorted({r['pkt_rate'] for r in rows})
    schemes = sorted({r['scheme'] for r in rows})

    for rate in rates:
        fig, axes = plt.subplots(2, 2, figsize=(12, 9))
        fig.suptitle(f'Performance vs Slotframe Length (rate={rate} pkt/min)',
                     fontsize=14, fontweight='bold', y=0.98)

        for idx, (key, title, ylabel) in enumerate(METRICS):
            ax = axes[idx // 2][idx % 2]
            for scheme in schemes:
                st = SCHEME_STYLES.get(scheme, {'color': 'gray', 'marker': 'x',
                                                 'ls': ':', 'label': scheme})
                vals = [by_sf[key][scheme].get(rate, {}).get(sf, 0) for sf in sfs]
                ax.plot(sfs, vals, marker=st['marker'], color=st['color'],
                        linestyle=st['ls'], linewidth=2, markersize=8,
                        label=st['label'])
            ax.set_xlabel('Slotframe Length', fontsize=11)
            ax.set_ylabel(ylabel, fontsize=11)
            ax.set_title(title, fontsize=12)
            ax.set_xticks(sfs)
            ax.legend(fontsize=9, loc='best')
            ax.grid(True, alpha=0.3)

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        path = os.path.join(output_dir, f'comparison_vs_sf_rate{rate}.png')
        plt.savefig(path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f'Saved: {path}')


def plot_vs_rate(rows, output_dir):
    """2x2: x-axis = packet rate, one line per scheme, grouped by SF."""
    _, by_rate = organize(rows)
    sfs = sorted({r['sf_length'] for r in rows})
    rates = sorted({r['pkt_rate'] for r in rows})
    schemes = sorted({r['scheme'] for r in rows})

    for sf in sfs:
        fig, axes = plt.subplots(2, 2, figsize=(12, 9))
        fig.suptitle(f'Performance vs Packet Rate (SF={sf})',
                     fontsize=14, fontweight='bold', y=0.98)

        for idx, (key, title, ylabel) in enumerate(METRICS):
            ax = axes[idx // 2][idx % 2]
            for scheme in schemes:
                st = SCHEME_STYLES.get(scheme, {'color': 'gray', 'marker': 'x',
                                                 'ls': ':', 'label': scheme})
                vals = [by_rate[key][scheme].get(sf, {}).get(r, 0) for r in rates]
                ax.plot(rates, vals, marker=st['marker'], color=st['color'],
                        linestyle=st['ls'], linewidth=2, markersize=8,
                        label=st['label'])
            ax.set_xlabel('Packet Rate (pkt/min)', fontsize=11)
            ax.set_ylabel(ylabel, fontsize=11)
            ax.set_title(title, fontsize=12)
            ax.set_xticks(rates)
            ax.legend(fontsize=9, loc='best')
            ax.grid(True, alpha=0.3)

        plt.tight_layout(rect=[0, 0, 1, 0.95])
        path = os.path.join(output_dir, f'comparison_vs_rate_sf{sf}.png')
        plt.savefig(path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f'Saved: {path}')


def plot_individual(rows, output_dir):
    """One plot per metric: x=SF, lines=schemes, one figure per rate."""
    by_sf, by_rate = organize(rows)
    sfs = sorted({r['sf_length'] for r in rows})
    rates = sorted({r['pkt_rate'] for r in rows})
    schemes = sorted({r['scheme'] for r in rows})

    for key, title, ylabel in METRICS:
        # vs SF for each rate
        for rate in rates:
            fig, ax = plt.subplots(figsize=(7, 5))
            for scheme in schemes:
                st = SCHEME_STYLES.get(scheme, {'color': 'gray', 'marker': 'x',
                                                 'ls': ':', 'label': scheme})
                vals = [by_sf[key][scheme].get(rate, {}).get(sf, 0) for sf in sfs]
                ax.plot(sfs, vals, marker=st['marker'], color=st['color'],
                        linestyle=st['ls'], linewidth=2, markersize=8,
                        label=st['label'])
            ax.set_xlabel('Slotframe Length', fontsize=12)
            ax.set_ylabel(ylabel, fontsize=12)
            ax.set_title(f'{title} vs SF (rate={rate} pkt/min)', fontsize=13)
            ax.set_xticks(sfs)
            ax.legend(fontsize=10)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            path = os.path.join(output_dir, f'{key}_vs_sf_rate{rate}.png')
            plt.savefig(path, dpi=300, bbox_inches='tight')
            plt.close()

        # vs rate for each SF
        for sf in sfs:
            fig, ax = plt.subplots(figsize=(7, 5))
            for scheme in schemes:
                st = SCHEME_STYLES.get(scheme, {'color': 'gray', 'marker': 'x',
                                                 'ls': ':', 'label': scheme})
                vals = [by_rate[key][scheme].get(sf, {}).get(r, 0) for r in rates]
                ax.plot(rates, vals, marker=st['marker'], color=st['color'],
                        linestyle=st['ls'], linewidth=2, markersize=8,
                        label=st['label'])
            ax.set_xlabel('Packet Rate (pkt/min)', fontsize=12)
            ax.set_ylabel(ylabel, fontsize=12)
            ax.set_title(f'{title} vs Rate (SF={sf})', fontsize=13)
            ax.set_xticks(rates)
            ax.legend(fontsize=10)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            path = os.path.join(output_dir, f'{key}_vs_rate_sf{sf}.png')
            plt.savefig(path, dpi=300, bbox_inches='tight')
            plt.close()

    print(f'Individual plots saved to {output_dir}/')


def main():
    parser = argparse.ArgumentParser(description='Plot EASE vs Orchestra results')
    parser.add_argument('--csv', default=DEFAULT_CSV)
    parser.add_argument('--output', default=OUTPUT_DIR)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if not os.path.exists(args.csv):
        print(f'CSV not found: {args.csv}')
        print('Run evaluation first: python3 run_evaluation.py')
        return

    rows = load_csv(args.csv)
    print(f'Loaded {len(rows)} data points from {args.csv}')

    plot_vs_sf(rows, args.output)
    plot_vs_rate(rows, args.output)
    plot_individual(rows, args.output)

    print(f'\nAll plots saved to {args.output}/')


if __name__ == '__main__':
    main()
