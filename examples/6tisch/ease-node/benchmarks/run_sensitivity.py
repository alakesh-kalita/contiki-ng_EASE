#!/usr/bin/env python3
"""
CUSUM Parameter Sensitivity Analysis.

Varies H and rho while keeping everything else constant.
Uses the same infrastructure as run_evaluation.py but only modifies
EASE_CONF_CUSUM_THRESHOLD and EASE_CONF_CUSUM_RHO in project-conf.h.

Usage:
    python3 run_sensitivity.py
    python3 run_sensitivity.py --parse-only
"""

import os
import re
import csv
import argparse
import subprocess
import shutil
import time
from collections import defaultdict

# ---------------------------------------------------------------------------
# Paths — all absolute to avoid directory confusion
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
CONTIKI_DIR = os.path.abspath(os.path.join(PROJECT_DIR, '..', '..', '..'))
COOJA_DIR = os.path.join(CONTIKI_DIR, 'tools', 'cooja')
CSC_TEMPLATE = os.path.join(PROJECT_DIR, 'ease-25node.csc')
CONF_PATH = os.path.join(PROJECT_DIR, 'project-conf.h')
MAKE_PATH = os.path.join(PROJECT_DIR, 'Makefile')
BUILD_DIR = os.path.join(PROJECT_DIR, 'build')
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'evaluation_results', 'sensitivity')

# ---------------------------------------------------------------------------
# Fixed parameters
# ---------------------------------------------------------------------------
SF = 101
RATE = 4
SIM_DURATION_MS = 30 * 60 * 1000
WARMUP_US = 10 * 60 * 1_000_000
CLOCK_SECOND = 1000
ROOT_ID = 1

# Sensitivity matrix
H_VALUES = [200, 500, 1000]
RHO_VALUES = [50, 80, 90]

# ---------------------------------------------------------------------------
# The ONE project-conf.h template — only H and rho are substituted
# ---------------------------------------------------------------------------
EASE_CONF = """\
#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_
#define IEEE802154_CONF_PANID 0x81a5
#define TSCH_CONF_AUTOSTART 0
#define SICSLOWPAN_CONF_FRAG 1
#define UIP_CONF_BUFFER_SIZE 240
#ifndef EASE_CONF_UNICAST_PERIOD
#define EASE_CONF_UNICAST_PERIOD       {sf}
#endif
#ifndef EASE_PACKETS_PER_MIN
#define EASE_PACKETS_PER_MIN           {rate}
#endif
#define EASE_CONF_RDC_BUDGET_PCT       20
#define EASE_CONF_CUSUM_THRESHOLD      {H}
#define EASE_CONF_CUSUM_RHO            {rho}
#define EASE_CONF_MAX_CHILDREN         25
#define EASE_CONF_WITH_GAME_THEORY     1
#define EASE_CONF_NUM_CHANNELS         16
#define ORCHESTRA_CONF_RULES {{ &eb_per_time_source, \\
                               &ease_dedicated_cell, \\
                               &ease_shared_cell, \\
                               &default_common }}
#define TSCH_CALLBACK_DO_NACK ease_do_nack
#define TSCH_CALLBACK_NEW_TIME_SOURCE orchestra_callback_new_time_source
#define TSCH_CALLBACK_PACKET_READY orchestra_callback_packet_ready
#define TSCH_CALLBACK_ROOT_NODE_UPDATED orchestra_callback_root_node_updated
#define NETSTACK_CONF_ROUTING_NEIGHBOR_ADDED_CALLBACK orchestra_callback_child_added
#define NETSTACK_CONF_ROUTING_NEIGHBOR_REMOVED_CALLBACK orchestra_callback_child_removed
#define NETSTACK_CONF_DS6_NEIGHBOR_UPDATED_CALLBACK orchestra_callback_neighbor_updated
#define RPL_CONF_MOP RPL_MOP_STORING_NO_MULTICAST
#define TSCH_SCHEDULE_CONF_MAX_LINKS 128
#define TSCH_SCHEDULE_CONF_MAX_SLOTFRAMES 6
#define TSCH_CONF_DEFAULT_HOPPING_SEQUENCE TSCH_HOPPING_SEQUENCE_16_16
#define ENERGEST_CONF_ON               1
#define LOG_CONF_LEVEL_RPL                         LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_TCPIP                       LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_IPV6                        LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_6LOWPAN                     LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_MAC                         LOG_LEVEL_INFO
#define TSCH_LOG_CONF_PER_SLOT                     0
#endif
"""

MAKEFILE_EASE = """\
CONTIKI_PROJECT = node
all: $(CONTIKI_PROJECT)
PLATFORMS_EXCLUDE = sky native
CONTIKI=../../..
MAKE_MAC = MAKE_MAC_TSCH
MAKE_ROUTING = MAKE_ROUTING_RPL_CLASSIC
include $(CONTIKI)/Makefile.dir-variables
include $(CONTIKI)/Makefile.identify-target
MODULES += $(CONTIKI_NG_SERVICES_DIR)/orchestra
MODULES += $(CONTIKI_NG_SERVICES_DIR)/ease
ifneq ($(TARGET),z1)
MODULES += $(CONTIKI_NG_SERVICES_DIR)/shell
endif
include $(CONTIKI)/Makefile.include
"""


# ---------------------------------------------------------------------------
# CSC with ScriptRunner
# ---------------------------------------------------------------------------
def create_csc(output_path):
    with open(CSC_TEMPLATE, 'r') as f:
        csc = f.read()
    if 'ScriptRunner' not in csc:
        plugin = (
            '  <plugin>\n'
            '    org.contikios.cooja.plugins.ScriptRunner\n'
            '    <plugin_config>\n'
            '      <script>TIMEOUT({timeout}, log.testOK());&#xD;\n'
            '&#xD;\nwhile(true) {{&#xD;\n'
            '  if(msg) {{&#xD;\n'
            '    log.log(time + " " + id + " " + msg + "\\n");&#xD;\n'
            '  }}&#xD;\n  YIELD();&#xD;\n}}</script>\n'
            '      <active>true</active>\n'
            '    </plugin_config>\n'
            '    <bounds x="400" y="0" height="600" width="800" />\n'
            '  </plugin>\n'
        ).format(timeout=SIM_DURATION_MS)
        csc = csc.replace('</simconf>', plugin + '</simconf>')
    with open(output_path, 'w') as f:
        f.write(csc)


# ---------------------------------------------------------------------------
# Run one Cooja simulation
# ---------------------------------------------------------------------------
def run_cooja(logdir, csc_path):
    os.makedirs(logdir, exist_ok=True)
    testlog = os.path.join(logdir, 'COOJA.testlog')
    if os.path.exists(testlog):
        os.remove(testlog)

    cmd = (
        "cd {cooja} && ./gradlew --no-watch-fs --parallel --build-cache "
        "run --args='--contiki={contiki} --no-gui --logdir={logdir} {csc}'"
    ).format(cooja=COOJA_DIR, contiki=CONTIKI_DIR,
             logdir=logdir, csc=csc_path)

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=7200)
    except subprocess.TimeoutExpired:
        return None, 0

    elapsed = time.time() - t0
    if not os.path.exists(testlog):
        return None, elapsed
    return testlog, elapsed


# ---------------------------------------------------------------------------
# Parse and compute
# ---------------------------------------------------------------------------
def parse_and_compute(testlog_path):
    tx_events = {}
    rx_events = {}
    energest = defaultdict(list)

    re_tx = re.compile(r'PERF-TX src=(\d+) seq=(\d+) tx_ticks=(\d+)')
    re_rx = re.compile(r'PERF-RX src=(\d+) seq=(\d+) tx_ticks=(\d+) rx_ticks=(\d+)')
    re_en = re.compile(
        r'ENERGEST node=(\d+) cpu=(\d+) lpm=(\d+) tx=(\d+) listen=(\d+) total=(\d+)')

    with open(testlog_path, 'r', errors='replace') as f:
        for line in f:
            parts = line.strip().split(None, 2)
            if len(parts) < 3:
                continue
            try:
                ts_us = int(parts[0])
            except ValueError:
                continue
            if ts_us < WARMUP_US:
                continue
            msg = parts[2]

            m = re_tx.search(msg)
            if m:
                tx_events[(int(m.group(1)), int(m.group(2)))] = int(m.group(3))
                continue
            m = re_rx.search(msg)
            if m:
                rx_events[(int(m.group(1)), int(m.group(2)))] = (
                    int(m.group(3)), int(m.group(4)))
                continue
            m = re_en.search(msg)
            if m:
                energest[int(m.group(1))].append(
                    (int(m.group(4)), int(m.group(5)), int(m.group(6))))

    ntx = len(tx_events)
    nrx = len(rx_events)
    pdr = nrx / ntx * 100.0 if ntx > 0 else 0.0

    lats = [(rt - tt) * 1000.0 / CLOCK_SECOND
            for (_, _), (tt, rt) in rx_events.items() if rt >= tt]
    avg_lat = sum(lats) / len(lats) if lats else 0.0

    rdcs = []
    for nid, recs in energest.items():
        if nid == ROOT_ID:
            continue
        s_tx = sum(r[0] for r in recs)
        s_li = sum(r[1] for r in recs)
        s_to = sum(r[2] for r in recs)
        if s_to > 0:
            rdcs.append((s_tx + s_li) / s_to * 100.0)
    avg_rdc = sum(rdcs) / len(rdcs) if rdcs else 0.0

    senders = len(set(k[0] for k in rx_events))

    return {
        'pdr': round(pdr, 2),
        'rdc': round(avg_rdc, 3),
        'lat': round(avg_lat, 1),
        'tx': ntx,
        'rx': nrx,
        'senders': senders,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='CUSUM Sensitivity Analysis')
    parser.add_argument('--parse-only', action='store_true',
                        help='Only parse existing logs')
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    configs = [(H, rho) for H in H_VALUES for rho in RHO_VALUES]
    total = len(configs)
    results = []

    # Backup originals
    conf_bak = CONF_PATH + '._sensitivity_bak'
    make_bak = MAKE_PATH + '._sensitivity_bak'
    shutil.copy2(CONF_PATH, conf_bak)
    shutil.copy2(MAKE_PATH, make_bak)

    # CSC file (absolute path, persists through all runs)
    csc_path = os.path.join(PROJECT_DIR, '_sensitivity_eval.csc')

    try:
        if not args.parse_only:
            # Ensure EASE Makefile
            with open(MAKE_PATH, 'w') as f:
                f.write(MAKEFILE_EASE)

            # Create CSC once
            create_csc(csc_path)

            for idx, (H, rho) in enumerate(configs, 1):
                print('\n' + '=' * 55)
                print('  [{}/{}] H={} rho={:.2f} (SF={}, rate={})'.format(
                      idx, total, H, rho / 100, SF, RATE))
                print('=' * 55)

                # Write project-conf.h with this H and rho
                with open(CONF_PATH, 'w') as f:
                    f.write(EASE_CONF.format(sf=SF, rate=RATE, H=H, rho=rho))

                # Clean build (absolute path)
                if os.path.exists(BUILD_DIR):
                    shutil.rmtree(BUILD_DIR)

                logdir = os.path.join(RESULTS_DIR,
                                      'H{}_rho{}'.format(H, rho))

                testlog, elapsed = run_cooja(logdir, csc_path)
                print('  Cooja: {:.0f}s'.format(elapsed))

                if testlog is None:
                    print('  FAILED')
                    results.append({
                        'H': H, 'rho': rho / 100,
                        'pdr': 0, 'rdc': 0, 'lat': 0,
                        'tx': 0, 'rx': 0, 'senders': 0})
                    continue

                m = parse_and_compute(testlog)
                m['H'] = H
                m['rho'] = rho / 100
                results.append(m)
                print('  PDR={:.1f}%  RDC={:.2f}%  Lat={:.0f}ms  '
                      'Senders={}'.format(
                      m['pdr'], m['rdc'], m['lat'], m['senders']))

        else:
            for H, rho in configs:
                logdir = os.path.join(RESULTS_DIR,
                                      'H{}_rho{}'.format(H, rho))
                testlog = os.path.join(logdir, 'COOJA.testlog')
                if not os.path.exists(testlog):
                    print('  No log: H={} rho={}'.format(H, rho))
                    results.append({
                        'H': H, 'rho': rho / 100,
                        'pdr': 0, 'rdc': 0, 'lat': 0,
                        'tx': 0, 'rx': 0, 'senders': 0})
                    continue
                m = parse_and_compute(testlog)
                m['H'] = H
                m['rho'] = rho / 100
                results.append(m)

    finally:
        # Always restore originals
        shutil.copy2(conf_bak, CONF_PATH)
        shutil.copy2(make_bak, MAKE_PATH)
        for f in [conf_bak, make_bak]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(csc_path):
            os.remove(csc_path)
        print('\n  Original project-conf.h and Makefile restored.')

    # Print table
    hdr = '{:>6} {:>5} {:>7} {:>7} {:>9} {:>6} {:>6} {:>8}'.format(
          'H', 'rho', 'PDR%', 'RDC%', 'Lat(ms)', 'TX', 'RX', 'Senders')
    sep = '-' * len(hdr)
    print('\n' + sep)
    print('  CUSUM Sensitivity (SF={}, rate={} pkt/min)'.format(SF, RATE))
    print(sep)
    print(hdr)
    print(sep)
    for r in results:
        print('{:>6} {:>5.2f} {:>7.2f} {:>7.3f} {:>9.1f} {:>6} {:>6} {:>8}'.format(
              r['H'], r['rho'], r['pdr'], r['rdc'], r['lat'],
              r['tx'], r['rx'], r['senders']))
    print(sep)

    # Write CSV
    csv_path = os.path.join(RESULTS_DIR, 'cusum_sensitivity.csv')
    fieldnames = ['H', 'rho', 'pdr', 'rdc', 'lat', 'tx', 'rx', 'senders']
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print('\nCSV: {}'.format(csv_path))


if __name__ == '__main__':
    main()
