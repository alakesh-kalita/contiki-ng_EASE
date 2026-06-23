#!/usr/bin/env python3
"""
EASE Performance Evaluation: EASE vs Orchestra-RB vs Orchestra-SB.

Runs Cooja simulations for each (scheme, slotframe_length, packet_rate),
parses logs from last 20 min of 30-min simulation (10-min warmup),
computes PDR, RDC, E2E Latency, Channel Utilization.

Usage:
    python3 run_evaluation.py                        # all schemes, all configs
    python3 run_evaluation.py --scheme ease           # EASE only
    python3 run_evaluation.py --scheme orchestra-sb   # Orchestra sender-based only
    python3 run_evaluation.py --sf 101 --rate 4       # single config
    python3 run_evaluation.py --parse-only            # parse existing logs
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
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
CONTIKI_DIR = os.path.abspath(os.path.join(PROJECT_DIR, '..', '..', '..'))
COOJA_DIR = os.path.join(CONTIKI_DIR, 'tools', 'cooja')
CSC_TEMPLATE = os.path.join(PROJECT_DIR, 'ease-25node.csc')
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'evaluation_results')

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
SLOTFRAME_LENGTHS = [101, 131]
PACKET_RATES = [4, 10]
SCHEMES = ['ease', 'orchestra-rb', 'orchestra-sb']
ROOT_ID = 1

# 30 min sim, 10 min warmup, analyze last 20 min
SIM_DURATION_MS = 30 * 60 * 1000
WARMUP_US = 10 * 60 * 1_000_000
CLOCK_SECOND = 1000

# ---------------------------------------------------------------------------
# Project-conf templates
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
#define EASE_CONF_CUSUM_THRESHOLD      500
#define EASE_CONF_CUSUM_RHO            80
#define EASE_CONF_MAX_CHILDREN         25
#define EASE_CONF_WITH_GAME_THEORY     1
#define EASE_CONF_NUM_CHANNELS         16

#define ORCHESTRA_CONF_RULES {{ &eb_per_time_source, \\
                               &ease_dedicated_cell, \\
                               &ease_shared_cell, \\
                               &default_common }}

#define TSCH_CALLBACK_DO_NACK ease_do_nack
#define TSCH_CALLBACK_EACK_NACK_RECEIVED ease_notify_budget_exhausted
#define TSCH_CALLBACK_NEW_TIME_SOURCE orchestra_callback_new_time_source
#define TSCH_CALLBACK_PACKET_READY orchestra_callback_packet_ready
#define TSCH_CALLBACK_ROOT_NODE_UPDATED orchestra_callback_root_node_updated
#define NETSTACK_CONF_ROUTING_NEIGHBOR_ADDED_CALLBACK orchestra_callback_child_added
#define NETSTACK_CONF_ROUTING_NEIGHBOR_REMOVED_CALLBACK orchestra_callback_child_removed
#define NETSTACK_CONF_DS6_NEIGHBOR_UPDATED_CALLBACK orchestra_callback_neighbor_updated

#define RPL_CONF_MOP RPL_MOP_STORING_NO_MULTICAST
#define TSCH_SCHEDULE_CONF_MAX_LINKS 256
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

ORCHESTRA_SB_CONF = """\
#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_

#define IEEE802154_CONF_PANID 0x81a5
#define TSCH_CONF_AUTOSTART 0
#define SICSLOWPAN_CONF_FRAG 1
#define UIP_CONF_BUFFER_SIZE 240

#ifndef EASE_PACKETS_PER_MIN
#define EASE_PACKETS_PER_MIN           {rate}
#endif
#ifndef ORCHESTRA_CONF_UNICAST_PERIOD
#define ORCHESTRA_CONF_UNICAST_PERIOD  {sf}
#endif

#define ORCHESTRA_CONF_RULES {{ &eb_per_time_source, \\
                               &unicast_per_neighbor_rpl_storing, \\
                               &default_common }}

#define TSCH_CALLBACK_NEW_TIME_SOURCE orchestra_callback_new_time_source
#define TSCH_CALLBACK_PACKET_READY orchestra_callback_packet_ready
#define TSCH_CALLBACK_ROOT_NODE_UPDATED orchestra_callback_root_node_updated
#define NETSTACK_CONF_ROUTING_NEIGHBOR_ADDED_CALLBACK orchestra_callback_child_added
#define NETSTACK_CONF_ROUTING_NEIGHBOR_REMOVED_CALLBACK orchestra_callback_child_removed
#define NETSTACK_CONF_DS6_NEIGHBOR_UPDATED_CALLBACK orchestra_callback_neighbor_updated

#define RPL_CONF_MOP RPL_MOP_STORING_NO_MULTICAST
#define TSCH_SCHEDULE_CONF_MAX_LINKS 256
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

ORCHESTRA_RB_CONF = """\
#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_

#define IEEE802154_CONF_PANID 0x81a5
#define TSCH_CONF_AUTOSTART 0
#define SICSLOWPAN_CONF_FRAG 1
#define UIP_CONF_BUFFER_SIZE 240

#ifndef EASE_PACKETS_PER_MIN
#define EASE_PACKETS_PER_MIN           {rate}
#endif
#ifndef ORCHESTRA_CONF_UNICAST_PERIOD
#define ORCHESTRA_CONF_UNICAST_PERIOD  {sf}
#endif

#define ORCHESTRA_CONF_RULES {{ &eb_per_time_source, \\
                               &unicast_per_neighbor_rpl_ns, \\
                               &default_common }}

#define TSCH_CALLBACK_NEW_TIME_SOURCE orchestra_callback_new_time_source
#define TSCH_CALLBACK_PACKET_READY orchestra_callback_packet_ready
#define TSCH_CALLBACK_ROOT_NODE_UPDATED orchestra_callback_root_node_updated
#define NETSTACK_CONF_ROUTING_NEIGHBOR_ADDED_CALLBACK orchestra_callback_child_added
#define NETSTACK_CONF_ROUTING_NEIGHBOR_REMOVED_CALLBACK orchestra_callback_child_removed
#define NETSTACK_CONF_DS6_NEIGHBOR_UPDATED_CALLBACK orchestra_callback_neighbor_updated

#define RPL_CONF_MOP RPL_MOP_STORING_NO_MULTICAST
#define TSCH_SCHEDULE_CONF_MAX_LINKS 256
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

CONF_TEMPLATES = {
    'ease': EASE_CONF,
    'orchestra-sb': ORCHESTRA_SB_CONF,
    'orchestra-rb': ORCHESTRA_RB_CONF,
}

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

MAKEFILE_ORCHESTRA = """\
CONTIKI_PROJECT = node
all: $(CONTIKI_PROJECT)
PLATFORMS_EXCLUDE = sky native
CONTIKI=../../..
MAKE_MAC = MAKE_MAC_TSCH
MAKE_ROUTING = MAKE_ROUTING_RPL_CLASSIC
include $(CONTIKI)/Makefile.dir-variables
include $(CONTIKI)/Makefile.identify-target
MODULES += $(CONTIKI_NG_SERVICES_DIR)/orchestra
ifneq ($(TARGET),z1)
MODULES += $(CONTIKI_NG_SERVICES_DIR)/shell
endif
include $(CONTIKI)/Makefile.include
"""

SCRIPT_RUNNER = """\
  <plugin>
    org.contikios.cooja.plugins.ScriptRunner
    <plugin_config>
      <script>TIMEOUT({timeout}, log.testOK());&#xD;
&#xD;
while(true) {{&#xD;
  if(msg) {{&#xD;
    log.log(time + " " + id + " " + msg + "\\n");&#xD;
  }}&#xD;
  YIELD();&#xD;
}}</script>
      <active>true</active>
    </plugin_config>
    <bounds x="400" y="0" height="600" width="800" />
  </plugin>
"""


# ---------------------------------------------------------------------------
# CSC generation
# ---------------------------------------------------------------------------
def generate_csc(output_path, timeout_ms=SIM_DURATION_MS):
    """Generate CSC with ScriptRunner for headless mode."""
    with open(CSC_TEMPLATE, 'r') as f:
        content = f.read()
    if 'ScriptRunner' not in content:
        plugin = SCRIPT_RUNNER.format(timeout=timeout_ms)
        content = content.replace('</simconf>', plugin + '</simconf>')
    else:
        content = re.sub(r'TIMEOUT\(\d+', 'TIMEOUT({}'.format(timeout_ms), content)
    with open(output_path, 'w') as f:
        f.write(content)


def setup_scheme(scheme, sf, rate):
    """Write project-conf.h and Makefile for the given scheme."""
    conf_path = os.path.join(PROJECT_DIR, 'project-conf.h')
    make_path = os.path.join(PROJECT_DIR, 'Makefile')

    with open(conf_path, 'w') as f:
        f.write(CONF_TEMPLATES[scheme].format(sf=sf, rate=rate))

    with open(make_path, 'w') as f:
        f.write(MAKEFILE_EASE if scheme == 'ease' else MAKEFILE_ORCHESTRA)


# ---------------------------------------------------------------------------
# Build and run
# ---------------------------------------------------------------------------
def run_cooja(logdir, csc_path):
    """Run Cooja headless. Returns path to COOJA.testlog or None."""
    os.makedirs(logdir, exist_ok=True)
    testlog = os.path.join(logdir, 'COOJA.testlog')
    if os.path.exists(testlog):
        os.remove(testlog)

    cooja_args = ('--contiki={} --no-gui --logdir={} {}'.format(
                  CONTIKI_DIR, logdir, csc_path))
    cmd = ("cd {} && ./gradlew --no-watch-fs --parallel "
           "--build-cache run --args='{}'".format(COOJA_DIR, cooja_args))

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=7200)
    except subprocess.TimeoutExpired:
        print('  ERROR: wall-clock timeout')
        return None

    elapsed = time.time() - t0
    print('  Finished in {:.0f}s (rc={})'.format(elapsed, proc.returncode))

    if not os.path.exists(testlog):
        if proc.stderr:
            print('  STDERR: {}'.format(proc.stderr[-300:]))
        return None
    return testlog


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------
def parse_log(testlog_path):
    """Parse COOJA.testlog. Skip warmup period. Return tx, rx, energest."""
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

    # Count parent switches from full log
    parent_switches = 0
    with open(testlog_path, 'r', errors='replace') as f:
        for line in f:
            if 'Parent switch' in line:
                parent_switches += 1

    return tx_events, rx_events, energest, parent_switches


def compute_metrics(tx_events, rx_events, energest, sf_length, pkt_rate, scheme,
                    parent_switches=0):
    """Compute PDR, RDC, latency, channel utilization."""
    total_tx = len(tx_events)
    total_rx = len(rx_events)
    pdr = (total_rx / total_tx * 100.0) if total_tx > 0 else 0.0

    latencies = []
    for (src, seq), (tx_t, rx_t) in rx_events.items():
        if rx_t >= tx_t:
            latencies.append((rx_t - tx_t) * 1000.0 / CLOCK_SECOND)
    avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0

    rdc_values = []
    for nid, records in energest.items():
        if nid == ROOT_ID:
            continue
        s_tx = sum(r[0] for r in records)
        s_li = sum(r[1] for r in records)
        s_to = sum(r[2] for r in records)
        if s_to > 0:
            rdc_values.append((s_tx + s_li) / s_to * 100.0)
    avg_rdc = (sum(rdc_values) / len(rdc_values)) if rdc_values else 0.0

    all_tx = sum(sum(r[0] for r in recs) for recs in energest.values())
    all_to = sum(sum(r[2] for r in recs) for recs in energest.values())
    chan_util = (all_tx / all_to * 100.0) if all_to > 0 else 0.0

    return {
        'scheme': scheme,
        'sf_length': sf_length,
        'pkt_rate': pkt_rate,
        'pdr': round(pdr, 2),
        'avg_rdc': round(avg_rdc, 4),
        'avg_latency_ms': round(avg_latency, 2),
        'chan_util': round(chan_util, 4),
        'total_tx': total_tx,
        'total_rx': total_rx,
        'parent_switches': parent_switches,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def print_summary(results):
    """Print formatted results table."""
    hdr = ('{:<15} {:>4}  {:>5}  {:>7}  {:>7}  '
           '{:>9}  {:>8}  {:>6}  {:>6}  {:>6}'.format(
           'Scheme', 'SF', 'Rate', 'PDR%', 'RDC%',
           'Lat(ms)', 'ChUtil%', 'TX', 'RX', 'PSw'))
    sep = '-' * len(hdr)
    print('\n' + sep)
    print('  Performance Evaluation (last 20 min of 30-min sim)')
    print(sep)
    print(hdr)
    print(sep)
    for r in results:
        print('{:<15} {:>4}  {:>5}  {:>7.2f}  {:>7.3f}  '
              '{:>9.1f}  {:>8.3f}  {:>6}  {:>6}  {:>6}'.format(
              r['scheme'], r['sf_length'], r['pkt_rate'],
              r['pdr'], r['avg_rdc'],
              r['avg_latency_ms'], r['chan_util'],
              r['total_tx'], r['total_rx'],
              r['parent_switches']))
    print(sep)


def write_csv(results, csv_path):
    """Write results CSV."""
    fieldnames = ['scheme', 'sf_length', 'pkt_rate', 'pdr', 'avg_rdc',
                  'avg_latency_ms', 'chan_util', 'total_tx', 'total_rx',
                  'parent_switches']
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print('\nCSV: {}'.format(csv_path))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='EASE vs Orchestra Evaluation')
    parser.add_argument('--parse-only', action='store_true',
                        help='Only parse existing logs')
    parser.add_argument('--scheme', nargs='+', default=SCHEMES,
                        choices=SCHEMES, help='Schemes to evaluate')
    parser.add_argument('--sf', type=int, nargs='+', default=SLOTFRAME_LENGTHS,
                        help='Slotframe lengths')
    parser.add_argument('--rate', type=int, nargs='+', default=PACKET_RATES,
                        help='Packet rates (pkt/min)')
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Backup original files
    conf_orig = os.path.join(PROJECT_DIR, 'project-conf.h')
    make_orig = os.path.join(PROJECT_DIR, 'Makefile')
    conf_bak = conf_orig + '.eval_bak'
    make_bak = make_orig + '.eval_bak'
    shutil.copy2(conf_orig, conf_bak)
    shutil.copy2(make_orig, make_bak)

    configs = [(s, sf, r) for s in args.scheme
               for sf in args.sf for r in args.rate]
    total = len(configs)
    results = []

    csc_path = os.path.join(PROJECT_DIR, '_eval_temp.csc')

    try:
        if not args.parse_only:
            generate_csc(csc_path, SIM_DURATION_MS)

            for idx, (scheme, sf, rate) in enumerate(configs, 1):
                print('\n' + '=' * 60)
                print('  [{}/{}] {} SF={} rate={} pkt/min'.format(
                      idx, total, scheme, sf, rate))
                print('=' * 60)

                logdir = os.path.join(RESULTS_DIR,
                                      '{}_sf{}_rate{}'.format(scheme, sf, rate))

                setup_scheme(scheme, sf, rate)

                build_dir = os.path.join(SCRIPT_DIR, 'build')
                if os.path.exists(build_dir):
                    shutil.rmtree(build_dir)

                testlog = run_cooja(logdir, csc_path)
                if testlog is None:
                    print('  FAILED')
                    results.append({
                        'scheme': scheme, 'sf_length': sf, 'pkt_rate': rate,
                        'pdr': 0, 'avg_rdc': 0, 'avg_latency_ms': 0,
                        'chan_util': 0, 'total_tx': 0, 'total_rx': 0,
                        'parent_switches': 0})
                    continue

                tx, rx, en, psw = parse_log(testlog)
                m = compute_metrics(tx, rx, en, sf, rate, scheme, psw)
                results.append(m)
                print('  PDR={:.1f}%  RDC={:.2f}%  Lat={:.0f}ms'.format(
                      m['pdr'], m['avg_rdc'], m['avg_latency_ms']))

        else:
            for scheme, sf, rate in configs:
                logdir = os.path.join(RESULTS_DIR,
                                      '{}_sf{}_rate{}'.format(scheme, sf, rate))
                testlog = os.path.join(logdir, 'COOJA.testlog')
                if not os.path.exists(testlog):
                    print('  No log: {} SF={} rate={}'.format(scheme, sf, rate))
                    results.append({
                        'scheme': scheme, 'sf_length': sf, 'pkt_rate': rate,
                        'pdr': 0, 'avg_rdc': 0, 'avg_latency_ms': 0,
                        'chan_util': 0, 'total_tx': 0, 'total_rx': 0,
                        'parent_switches': 0})
                    continue
                tx, rx, en, psw = parse_log(testlog)
                m = compute_metrics(tx, rx, en, sf, rate, scheme, psw)
                results.append(m)

    finally:
        # Restore original files
        shutil.copy2(conf_bak, conf_orig)
        shutil.copy2(make_bak, make_orig)
        for f in [conf_bak, make_bak]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(csc_path):
            os.remove(csc_path)
        print('\n  Original project-conf.h and Makefile restored.')

    print_summary(results)
    csv_path = os.path.join(RESULTS_DIR, 'evaluation_results.csv')
    write_csv(results, csv_path)


if __name__ == '__main__':
    main()
