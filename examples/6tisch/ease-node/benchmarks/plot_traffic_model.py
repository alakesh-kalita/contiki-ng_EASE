#!/usr/bin/env python3
"""
Plot Traffic Model Comparison — two publication-quality PDF figures.

Figure 1: 2x2 grouped bar chart (PDR, RDC, Latency, Parent Switches)
          x-axis = SF, grouped by scheme, one subplot per traffic model row
Figure 2: 1x3 PDR-only bar chart (one panel per traffic model)

Usage:
    python3 plot_traffic_model.py
    python3 plot_traffic_model.py --csv path/to/traffic_model_results.csv
"""

import os
import csv
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Publication font settings
plt.rcParams.update({
    'font.size': 15,
    'font.family': 'serif',
    'axes.titlesize': 17,
    'axes.labelsize': 16,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 13,
    'legend.title_fontsize': 14,
    'figure.dpi': 300,
})

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(SCRIPT_DIR, 'evaluation_results', 'traffic_model',
                           'traffic_model_results.csv')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'evaluation_results')

TRAFFIC_ORDER = ['constant', 'poisson', 'onoff']
TRAFFIC_LABELS = {'constant': 'Constant', 'poisson': 'Poisson', 'onoff': 'ON/OFF'}

SCHEME_STYLE = {
    'ease':         {'color': '#2166ac', 'hatch': '',    'label': 'EASE'},
    'orchestra-sb': {'color': '#d6604d', 'hatch': '///', 'label': 'Orchestra-SB'},
}

METRICS = [
    ('pdr',              'Packet Delivery Ratio',  'PDR (%)'),
    ('rdc',              'Radio Duty Cycle',        'RDC (%)'),
    ('lat',              'End-to-End Latency',      'Latency (s)'),
    ('parent_switches',  'Parent Switches',         'Count'),
]


def load_csv(path):
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            rows.append({
                'scheme':  row['scheme'],
                'sf':      int(row['sf']),
                'traffic': row['traffic'],
                'pdr':     float(row['pdr']),
                'rdc':     float(row['rdc']),
                'lat':     float(row['lat']) / 1000.0,
                'parent_switches': int(row['parent_switches']),
            })
    return rows


def get_val(rows, scheme, sf, traffic, key):
    for r in rows:
        if r['scheme'] == scheme and r['sf'] == sf and r['traffic'] == traffic:
            return r[key]
    return 0


def figure1(rows, out_dir):
    """2×2 subplots. Each subplot: x = SF, grouped bars per scheme.
       Three bar clusters per SF (one per traffic model), side by side."""
    sfs = sorted(set(r['sf'] for r in rows))
    schemes = list(SCHEME_STYLE.keys())

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('EASE vs Orchestra-SB: Traffic Model Sensitivity',
                 fontsize=20, fontweight='bold', y=0.99)

    for midx, (key, title, ylabel) in enumerate(METRICS):
        ax = axes[midx // 2][midx % 2]

        n_sf = len(sfs)
        n_traffic = len(TRAFFIC_ORDER)
        n_scheme = len(schemes)
        total_bars = n_traffic * n_scheme
        bar_w = 0.12
        group_w = total_bars * bar_w

        for tidx, traffic in enumerate(TRAFFIC_ORDER):
            for sidx, scheme in enumerate(schemes):
                st = SCHEME_STYLE[scheme]
                vals = [get_val(rows, scheme, sf, traffic, key) for sf in sfs]
                offset = (tidx * n_scheme + sidx) * bar_w - group_w / 2 + bar_w / 2
                x = np.arange(n_sf) + offset

                label = '{} ({})'.format(st['label'], TRAFFIC_LABELS[traffic]) if midx == 0 else None
                ax.bar(x, vals, bar_w,
                       color=st['color'],
                       hatch=st['hatch'] if sidx == 1 else '',
                       edgecolor='black', linewidth=0.4,
                       alpha=0.7 + 0.15 * tidx,
                       label=label)

        ax.set_xticks(np.arange(n_sf))
        ax.set_xticklabels(['SF={}'.format(sf) for sf in sfs])
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, axis='y', alpha=0.25)

        if midx == 0:
            ax.legend(fontsize=10, ncol=2, loc='upper right',
                      framealpha=0.9)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    for ext in ['pdf', 'png']:
        p = os.path.join(out_dir, 'fig_traffic_all_metrics.{}'.format(ext))
        plt.savefig(p, bbox_inches='tight')
    plt.close()
    print('Saved: fig_traffic_all_metrics.pdf/png')


def figure2(rows, out_dir):
    """1×3 PDR comparison: one panel per traffic model, bars per SF × scheme."""
    sfs = sorted(set(r['sf'] for r in rows))
    schemes = list(SCHEME_STYLE.keys())

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), sharey=True)
    fig.suptitle('PDR Comparison under Different Traffic Models',
                 fontsize=19, fontweight='bold', y=1.01)

    width = 0.35
    x = np.arange(len(sfs))

    for tidx, traffic in enumerate(TRAFFIC_ORDER):
        ax = axes[tidx]

        for sidx, scheme in enumerate(schemes):
            st = SCHEME_STYLE[scheme]
            vals = [get_val(rows, scheme, sf, traffic, 'pdr') for sf in sfs]
            offset = [-width / 2, width / 2][sidx]

            bars = ax.bar(x + offset, vals, width,
                          color=st['color'],
                          hatch=st['hatch'],
                          edgecolor='black', linewidth=0.5,
                          label=st['label'], alpha=0.85)

            for bar, val in zip(bars, vals):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + 1.5,
                            '{:.0f}'.format(val),
                            ha='center', va='bottom',
                            fontsize=12, fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(['SF={}'.format(sf) for sf in sfs])
        ax.set_xlabel('Slotframe Length')
        ax.set_title('{} Traffic'.format(TRAFFIC_LABELS[traffic]),
                     fontsize=16)
        ax.set_ylim(0, 110)
        ax.grid(True, axis='y', alpha=0.3)

        if tidx == 0:
            ax.set_ylabel('PDR (%)')
            ax.legend(fontsize=13, loc='upper right')

    plt.tight_layout()
    for ext in ['pdf', 'png']:
        p = os.path.join(out_dir, 'fig_traffic_pdr.{}'.format(ext))
        plt.savefig(p, bbox_inches='tight')
    plt.close()
    print('Saved: fig_traffic_pdr.pdf/png')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', default=DEFAULT_CSV)
    parser.add_argument('--output', default=OUTPUT_DIR)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if not os.path.exists(args.csv):
        print('CSV not found: {}'.format(args.csv))
        print('Run: python3 run_traffic_model.py')
        return

    rows = load_csv(args.csv)
    print('Loaded {} data points'.format(len(rows)))

    figure1(rows, args.output)
    figure2(rows, args.output)

    print('\nAll plots in {}/'.format(args.output))


if __name__ == '__main__':
    main()
