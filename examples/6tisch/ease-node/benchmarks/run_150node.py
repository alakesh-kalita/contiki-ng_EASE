#!/usr/bin/env python3
"""
150-node scalability test: EASE vs Orchestra-SB vs Orchestra-RB.
Varies slotframe length and packet rate.
30-min simulation, 10-min warmup, analyze last 20 min.

Usage:
    python3 run_150node.py                    # all schemes, all configs
    python3 run_150node.py --scheme ease      # EASE only
    python3 run_150node.py --parse-only       # parse existing logs
"""

import os
import re
import csv
import math
import random
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
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'evaluation_results', '150node')

# ---------------------------------------------------------------------------
# Simulation parameters
# ---------------------------------------------------------------------------
NUM_NODES = 150
AREA_SIZE = 350.0       # 550m x 550m
TX_RANGE = 50.0
INTERFERENCE_RANGE = 50.0
RANDOM_SEED = 42

SLOTFRAME_LENGTHS = [101, 167]
PACKET_RATES = [4, 10]
SCHEMES = ['orchestra-sb', 'orchestra-rb', 'ease']

SIM_DURATION_MS = 30 * 60 * 1000    # 30 min
WARMUP_US = 10 * 60 * 1_000_000     # 10 min
CLOCK_SECOND = 1000
ROOT_ID = 1

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
#define EASE_PACKETS_PER_MIN {rate}
#define EASE_CONF_UNICAST_PERIOD {sf}
#define EASE_CONF_RDC_BUDGET_PCT 20
#define EASE_CONF_CUSUM_THRESHOLD 500
#define EASE_CONF_CUSUM_RHO 80
#define EASE_CONF_MAX_CHILDREN 30
#define EASE_CONF_WITH_GAME_THEORY 1
#define EASE_CONF_NUM_CHANNELS 16
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
#define TSCH_SCHEDULE_CONF_MAX_LINKS 256
#define TSCH_SCHEDULE_CONF_MAX_SLOTFRAMES 6
#define TSCH_CONF_DEFAULT_HOPPING_SEQUENCE TSCH_HOPPING_SEQUENCE_16_16
#define ENERGEST_CONF_ON 1
#define LOG_CONF_LEVEL_RPL LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_TCPIP LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_IPV6 LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_6LOWPAN LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_MAC LOG_LEVEL_INFO
#define TSCH_LOG_CONF_PER_SLOT 0
#endif
"""

ORCH_SB_CONF = """\
#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_
#define IEEE802154_CONF_PANID 0x81a5
#define TSCH_CONF_AUTOSTART 0
#define SICSLOWPAN_CONF_FRAG 1
#define UIP_CONF_BUFFER_SIZE 240
#define EASE_PACKETS_PER_MIN {rate}
#define ORCHESTRA_CONF_UNICAST_PERIOD {sf}
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
#define ENERGEST_CONF_ON 1
#define LOG_CONF_LEVEL_RPL LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_TCPIP LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_IPV6 LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_6LOWPAN LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_MAC LOG_LEVEL_INFO
#define TSCH_LOG_CONF_PER_SLOT 0
#endif
"""

ORCH_RB_CONF = ORCH_SB_CONF.replace(
    'unicast_per_neighbor_rpl_storing', 'unicast_per_neighbor_rpl_ns')

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

MAKEFILE_ORCH = MAKEFILE_EASE.replace(
    'MODULES += $(CONTIKI_NG_SERVICES_DIR)/ease\n', '')

CONF_MAP = {
    'ease':          (EASE_CONF,    MAKEFILE_EASE),
    'orchestra-sb':  (ORCH_SB_CONF, MAKEFILE_ORCH),
    'orchestra-rb':  (ORCH_RB_CONF, MAKEFILE_ORCH),
}

# ---------------------------------------------------------------------------
# CSC generation with 150 random nodes
# ---------------------------------------------------------------------------
def generate_150node_csc(output_path):
    """Generate a 150-node CSC with random positions and ScriptRunner."""
    random.seed(RANDOM_SEED)
    positions = [(0.0, 0.0)]  # Node 1 = root at origin
    for _ in range(NUM_NODES - 1):
        positions.append((random.uniform(0, AREA_SIZE),
                          random.uniform(0, AREA_SIZE)))

    # Verify connectivity
    visited = {0}
    queue = [0]
    while queue:
        n = queue.pop(0)
        for j in range(len(positions)):
            if j not in visited:
                dx = positions[n][0] - positions[j][0]
                dy = positions[n][1] - positions[j][1]
                if math.sqrt(dx*dx + dy*dy) <= TX_RANGE:
                    visited.add(j)
                    queue.append(j)
    print('  Topology: {}/{} nodes connected to root'.format(
          len(visited), NUM_NODES))

    # Build CSC XML
    mote_xml = []
    for i, (x, y) in enumerate(positions):
        mote_xml.append(
            '      <mote>\n'
            '        <interface_config>\n'
            '          org.contikios.cooja.interfaces.Position\n'
            '          <pos x="{:.1f}" y="{:.1f}" />\n'
            '        </interface_config>\n'
            '        <interface_config>\n'
            '          org.contikios.cooja.contikimote.interfaces.ContikiMoteID\n'
            '          <id>{}</id>\n'
            '        </interface_config>\n'
            '      </mote>'.format(x, y, i + 1))

    interfaces = [
        'org.contikios.cooja.interfaces.Position',
        'org.contikios.cooja.interfaces.Battery',
        'org.contikios.cooja.contikimote.interfaces.ContikiVib',
        'org.contikios.cooja.contikimote.interfaces.ContikiMoteID',
        'org.contikios.cooja.contikimote.interfaces.ContikiRS232',
        'org.contikios.cooja.contikimote.interfaces.ContikiBeeper',
        'org.contikios.cooja.interfaces.IPAddress',
        'org.contikios.cooja.contikimote.interfaces.ContikiRadio',
        'org.contikios.cooja.contikimote.interfaces.ContikiButton',
        'org.contikios.cooja.contikimote.interfaces.ContikiPIR',
        'org.contikios.cooja.contikimote.interfaces.ContikiClock',
        'org.contikios.cooja.contikimote.interfaces.ContikiLED',
        'org.contikios.cooja.contikimote.interfaces.ContikiCFS',
        'org.contikios.cooja.contikimote.interfaces.ContikiEEPROM',
        'org.contikios.cooja.interfaces.Mote2MoteRelations',
        'org.contikios.cooja.interfaces.MoteAttributes',
    ]
    iface_xml = '\n'.join(
        '      <moteinterface>{}</moteinterface>'.format(i) for i in interfaces)

    csc = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<simconf version="2023090101">\n'
           '  <simulation>\n'
           '    <title>EASE 150-Node Scalability</title>\n'
           '    <randomseed>{seed}</randomseed>\n'
           '    <motedelay_us>1000000</motedelay_us>\n'
           '    <radiomedium>\n'
           '      org.contikios.cooja.radiomediums.UDGM\n'
           '      <transmitting_range>{tx}</transmitting_range>\n'
           '      <interference_range>{interf}</interference_range>\n'
           '      <success_ratio_tx>1.0</success_ratio_tx>\n'
           '      <success_ratio_rx>1.0</success_ratio_rx>\n'
           '    </radiomedium>\n'
           '    <events>\n'
           '      <logoutput>40000</logoutput>\n'
           '    </events>\n'
           '    <motetype>\n'
           '      org.contikios.cooja.contikimote.ContikiMoteType\n'
           '      <description>EASE Node</description>\n'
           '      <source>[CONFIG_DIR]/node.c</source>\n'
           '      <commands>$(MAKE) -j$(CPUS) node.cooja TARGET=cooja</commands>\n'
           '{ifaces}\n'
           '      <symbols>false</symbols>\n'
           '{motes}\n'
           '    </motetype>\n'
           '  </simulation>\n'
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
           '</simconf>\n').format(
               seed=RANDOM_SEED, tx=TX_RANGE, interf=INTERFERENCE_RANGE,
               ifaces=iface_xml, motes='\n'.join(mote_xml),
               timeout=SIM_DURATION_MS)

    with open(output_path, 'w') as f:
        f.write(csc)
    print('  CSC: {} ({} nodes)'.format(output_path, NUM_NODES))

# ---------------------------------------------------------------------------
# Log parsing and metrics
# ---------------------------------------------------------------------------
def parse_log(path):
    tx, rx, energest = {}, {}, defaultdict(list)
    re_tx = re.compile(r'PERF-TX src=(\d+) seq=(\d+) tx_ticks=(\d+)')
    re_rx = re.compile(r'PERF-RX src=(\d+) seq=(\d+) tx_ticks=(\d+) rx_ticks=(\d+)')
    re_en = re.compile(r'ENERGEST node=(\d+) cpu=(\d+) lpm=(\d+) tx=(\d+) listen=(\d+) total=(\d+)')
    with open(path, 'r', errors='replace') as f:
        for line in f:
            parts = line.strip().split(None, 2)
            if len(parts) < 3:
                continue
            try:
                ts = int(parts[0])
            except ValueError:
                continue
            if ts < WARMUP_US:
                continue
            msg = parts[2]
            m = re_tx.search(msg)
            if m:
                tx[(int(m.group(1)), int(m.group(2)))] = int(m.group(3))
                continue
            m = re_rx.search(msg)
            if m:
                rx[(int(m.group(1)), int(m.group(2)))] = (int(m.group(3)), int(m.group(4)))
                continue
            m = re_en.search(msg)
            if m:
                energest[int(m.group(1))].append(
                    (int(m.group(4)), int(m.group(5)), int(m.group(6))))
    # Count parent switches from the full log (including warmup)
    parent_switches = 0
    with open(path, 'r', errors='replace') as f:
        for line in f:
            if 'Parent switch' in line:
                parent_switches += 1
    return tx, rx, energest, parent_switches


def compute_metrics(tx, rx, en, scheme, sf, rate, parent_switches=0):
    ntx, nrx = len(tx), len(rx)
    pdr = nrx / ntx * 100 if ntx > 0 else 0

    lats = [(rt - tt) * 1000.0 / CLOCK_SECOND
            for (_, _), (tt, rt) in rx.items() if rt >= tt]
    lat = sum(lats) / len(lats) if lats else 0

    rdcs = []
    for nid, recs in en.items():
        if nid == ROOT_ID:
            continue
        stx = sum(r[0] for r in recs)
        sli = sum(r[1] for r in recs)
        sto = sum(r[2] for r in recs)
        if sto > 0:
            rdcs.append((stx + sli) / sto * 100)
    rdc = sum(rdcs) / len(rdcs) if rdcs else 0

    all_tx = sum(sum(r[0] for r in recs) for recs in en.values())
    all_to = sum(sum(r[2] for r in recs) for recs in en.values())
    chutil = all_tx / all_to * 100 if all_to > 0 else 0

    senders = len(set(k[0] for k in rx))

    return {
        'scheme': scheme, 'sf': sf, 'rate': rate,
        'pdr': round(pdr, 2), 'rdc': round(rdc, 3),
        'lat': round(lat, 1), 'chutil': round(chutil, 4),
        'tx': ntx, 'rx': nrx, 'senders': senders,
        'parent_switches': parent_switches,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='150-node scalability test')
    parser.add_argument('--parse-only', action='store_true')
    parser.add_argument('--scheme', nargs='+', default=SCHEMES, choices=SCHEMES)
    parser.add_argument('--sf', type=int, nargs='+', default=SLOTFRAME_LENGTHS)
    parser.add_argument('--rate', type=int, nargs='+', default=PACKET_RATES)
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    configs = [(s, sf, r) for s in args.scheme
               for sf in args.sf for r in args.rate]
    total = len(configs)
    results = []

    # Backup
    conf_bak = os.path.join(SCRIPT_DIR, 'project-conf.h._150bak')
    make_bak = os.path.join(SCRIPT_DIR, 'Makefile._150bak')
    shutil.copy2(os.path.join(PROJECT_DIR, 'project-conf.h'), conf_bak)
    shutil.copy2(os.path.join(PROJECT_DIR, 'Makefile'), make_bak)

    csc_path = os.path.join(PROJECT_DIR, '_150node_eval.csc')

    try:
        if not args.parse_only:
            print('Generating 150-node topology...')
            generate_150node_csc(csc_path)

            for idx, (scheme, sf, rate) in enumerate(configs, 1):
                print('\n' + '=' * 65)
                print('  [{}/{}] {} SF={} rate={} pkt/min ({} nodes)'.format(
                      idx, total, scheme, sf, rate, NUM_NODES))
                print('=' * 65)

                conf_tpl, makefile = CONF_MAP[scheme]
                with open(os.path.join(PROJECT_DIR, 'project-conf.h'), 'w') as f:
                    f.write(conf_tpl.format(sf=sf, rate=rate))
                with open(os.path.join(PROJECT_DIR, 'Makefile'), 'w') as f:
                    f.write(makefile)

                build_dir = os.path.join(PROJECT_DIR, 'build')
                if os.path.exists(build_dir):
                    shutil.rmtree(build_dir)

                logdir = os.path.join(RESULTS_DIR,
                                      '{}_sf{}_rate{}'.format(scheme, sf, rate))
                os.makedirs(logdir, exist_ok=True)
                testlog = os.path.join(logdir, 'COOJA.testlog')
                if os.path.exists(testlog):
                    os.remove(testlog)

                cmd = ("cd {} && ./gradlew --no-watch-fs --parallel "
                       "--build-cache run --args='--contiki={} --no-gui "
                       "--logdir={} {}'".format(
                       COOJA_DIR, CONTIKI_DIR, logdir, csc_path))

                print('  Running Cooja...')
                t0 = time.time()
                try:
                    proc = subprocess.run(cmd, shell=True, capture_output=True,
                                          text=True, timeout=14400)
                except subprocess.TimeoutExpired:
                    print('  TIMEOUT (4h)')
                    results.append({'scheme': scheme, 'sf': sf, 'rate': rate,
                                    'pdr': 0, 'rdc': 0, 'lat': 0, 'chutil': 0,
                                    'tx': 0, 'rx': 0, 'senders': 0,
                                    'parent_switches': 0})
                    continue

                elapsed = time.time() - t0
                print('  Finished in {:.0f}s ({:.1f} min)'.format(
                      elapsed, elapsed / 60))

                if not os.path.exists(testlog):
                    print('  FAILED — no log')
                    if proc.stderr:
                        print('  {}'.format(proc.stderr[-200:]))
                    results.append({'scheme': scheme, 'sf': sf, 'rate': rate,
                                    'pdr': 0, 'rdc': 0, 'lat': 0, 'chutil': 0,
                                    'tx': 0, 'rx': 0, 'senders': 0,
                                    'parent_switches': 0})
                    continue

                tx, rx, en, psw = parse_log(testlog)
                m = compute_metrics(tx, rx, en, scheme, sf, rate, psw)
                results.append(m)
                print('  PDR={:.1f}%  RDC={:.2f}%  Lat={:.0f}ms  '
                      'Senders={}/{}  ParentSw={}'.format(
                      m['pdr'], m['rdc'], m['lat'], m['senders'],
                      NUM_NODES - 1, m['parent_switches']))

        else:
            for scheme, sf, rate in configs:
                logdir = os.path.join(RESULTS_DIR,
                                      '{}_sf{}_rate{}'.format(scheme, sf, rate))
                testlog = os.path.join(logdir, 'COOJA.testlog')
                if not os.path.exists(testlog):
                    print('  No log: {} SF={} rate={}'.format(scheme, sf, rate))
                    results.append({'scheme': scheme, 'sf': sf, 'rate': rate,
                                    'pdr': 0, 'rdc': 0, 'lat': 0, 'chutil': 0,
                                    'tx': 0, 'rx': 0, 'senders': 0,
                                    'parent_switches': 0})
                    continue
                tx, rx, en, psw = parse_log(testlog)
                m = compute_metrics(tx, rx, en, scheme, sf, rate, psw)
                results.append(m)

    finally:
        shutil.copy2(conf_bak, os.path.join(PROJECT_DIR, 'project-conf.h'))
        shutil.copy2(make_bak, os.path.join(PROJECT_DIR, 'Makefile'))
        for f in [conf_bak, make_bak]:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(csc_path):
            os.remove(csc_path)
        print('\n  Original files restored.')

    # Print results
    hdr = '{:<15} {:>4} {:>5} {:>7} {:>7} {:>9} {:>8} {:>6} {:>6} {:>8} {:>6}'.format(
          'Scheme', 'SF', 'Rate', 'PDR%', 'RDC%', 'Lat(ms)', 'ChUtil%',
          'TX', 'RX', 'Senders', 'PSw')
    sep = '-' * len(hdr)
    print('\n' + sep)
    print('  150-Node Scalability Results (30-min sim, 10-min warmup)')
    print(sep)
    print(hdr)
    print(sep)
    for r in results:
        print('{:<15} {:>4} {:>5} {:>7.2f} {:>7.3f} {:>9.1f} {:>8.4f} '
              '{:>6} {:>6} {:>8} {:>6}'.format(
              r['scheme'], r['sf'], r['rate'], r['pdr'], r['rdc'],
              r['lat'], r['chutil'], r['tx'], r['rx'], r['senders'],
              r['parent_switches']))
    print(sep)

    csv_path = os.path.join(RESULTS_DIR, 'results_150node.csv')
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=[
            'scheme', 'sf', 'rate', 'pdr', 'rdc', 'lat', 'chutil',
            'tx', 'rx', 'senders', 'parent_switches'])
        w.writeheader()
        w.writerows(results)
    print('\nCSV: {}'.format(csv_path))


if __name__ == '__main__':
    main()
