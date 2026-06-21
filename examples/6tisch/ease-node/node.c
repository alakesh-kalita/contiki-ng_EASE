/*
 * Copyright (c) 2024, EASE Authors.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 * 3. Neither the name of the Institute nor the names of its contributors
 *    may be used to endorse or promote products derived from this software
 *    without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE INSTITUTE AND CONTRIBUTORS ``AS IS'' AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED.  IN NO EVENT SHALL THE INSTITUTE OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
 * OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 * LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
 * OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
 * SUCH DAMAGE.
 */

#include "contiki.h"
#include "sys/node-id.h"
#include "sys/log.h"
#include "sys/energest.h"
#include "net/ipv6/uip-ds6-route.h"
#include "net/ipv6/simple-udp.h"
#include "net/mac/tsch/tsch.h"
#include "net/routing/routing.h"
#if BUILD_WITH_EASE
#include "ease.h"
#endif

#include <string.h>

#define LOG_MODULE "EASE-App"
#define LOG_LEVEL  LOG_LEVEL_INFO

#define UDP_CLIENT_PORT 8765
#define UDP_SERVER_PORT 5678

#ifndef EASE_PACKETS_PER_MIN
#define EASE_PACKETS_PER_MIN 4
#endif

#define SEND_INTERVAL ((60 * CLOCK_SECOND) / EASE_PACKETS_PER_MIN)
#define ENERGEST_INTERVAL (60 * CLOCK_SECOND)

struct perf_msg {
  uint16_t src_id;
  uint32_t seq;
  clock_time_t tx_ticks;
};

static struct simple_udp_connection udp_conn;
static uint32_t app_tx_count = 0;
static uint32_t app_rx_count = 0;

#if ENERGEST_CONF_ON
static uint64_t last_cpu, last_lpm, last_tx, last_listen, last_total;
#endif

/*---------------------------------------------------------------------------*/
PROCESS(node_process, "EASE Node");
AUTOSTART_PROCESSES(&node_process);
/*---------------------------------------------------------------------------*/
#if ENERGEST_CONF_ON
static void
print_energest(void)
{
  uint64_t curr_cpu, curr_lpm, curr_tx, curr_listen, curr_total;
  uint64_t d_cpu, d_lpm, d_tx, d_listen, d_total;

  energest_flush();

  curr_total = ENERGEST_GET_TOTAL_TIME();
  curr_cpu = energest_type_time(ENERGEST_TYPE_CPU);
  curr_lpm = energest_type_time(ENERGEST_TYPE_LPM);
  curr_tx = energest_type_time(ENERGEST_TYPE_TRANSMIT);
  curr_listen = energest_type_time(ENERGEST_TYPE_LISTEN);

  d_total = curr_total - last_total;
  d_cpu = curr_cpu - last_cpu;
  d_lpm = curr_lpm - last_lpm;
  d_tx = curr_tx - last_tx;
  d_listen = curr_listen - last_listen;

  if(d_total == 0) {
    d_total = 1;
  }

  LOG_INFO("ENERGEST node=%u cpu=%lu lpm=%lu tx=%lu listen=%lu total=%lu\n",
           node_id,
           (unsigned long)d_cpu, (unsigned long)d_lpm,
           (unsigned long)d_tx, (unsigned long)d_listen,
           (unsigned long)d_total);

  last_total = curr_total;
  last_cpu = curr_cpu;
  last_lpm = curr_lpm;
  last_tx = curr_tx;
  last_listen = curr_listen;
}
#endif
/*---------------------------------------------------------------------------*/
static void
udp_rx_callback(struct simple_udp_connection *c,
                const uip_ipaddr_t *sender_addr,
                uint16_t sender_port,
                const uip_ipaddr_t *receiver_addr,
                uint16_t receiver_port,
                const uint8_t *data,
                uint16_t datalen)
{
  struct perf_msg msg;

  app_rx_count++;

  if(datalen >= sizeof(msg)) {
    memcpy(&msg, data, sizeof(msg));
    LOG_INFO("PERF-RX src=%u seq=%lu tx_ticks=%lu rx_ticks=%lu\n",
             msg.src_id, (unsigned long)msg.seq,
             (unsigned long)msg.tx_ticks, (unsigned long)clock_time());
  }
}
/*---------------------------------------------------------------------------*/
PROCESS_THREAD(node_process, ev, data)
{
  static struct etimer send_timer;
#if ENERGEST_CONF_ON
  static struct etimer energest_timer;
#endif
  static struct perf_msg msg;
  uip_ipaddr_t dest_ipaddr;

  PROCESS_BEGIN();

#if CONTIKI_TARGET_COOJA || CONTIKI_TARGET_Z1
  if(node_id == 1) {
    NETSTACK_ROUTING.root_start();
  }
#endif

  if(node_id == 1) {
    simple_udp_register(&udp_conn, UDP_SERVER_PORT, NULL,
                         UDP_CLIENT_PORT, udp_rx_callback);
  } else {
    simple_udp_register(&udp_conn, UDP_CLIENT_PORT, NULL,
                         UDP_SERVER_PORT, udp_rx_callback);
  }

  NETSTACK_MAC.on();

#if ENERGEST_CONF_ON
  energest_flush();
  last_total = ENERGEST_GET_TOTAL_TIME();
  last_cpu = energest_type_time(ENERGEST_TYPE_CPU);
  last_lpm = energest_type_time(ENERGEST_TYPE_LPM);
  last_tx = energest_type_time(ENERGEST_TYPE_TRANSMIT);
  last_listen = energest_type_time(ENERGEST_TYPE_LISTEN);
  etimer_set(&energest_timer, ENERGEST_INTERVAL);
#endif

  etimer_set(&send_timer, SEND_INTERVAL);

  while(1) {
    PROCESS_WAIT_EVENT();

#if ENERGEST_CONF_ON
    if(etimer_expired(&energest_timer)) {
      print_energest();
      etimer_reset(&energest_timer);
    }
#endif

    if(etimer_expired(&send_timer)) {
      if(node_id != 1) {
        if(NETSTACK_ROUTING.node_is_reachable() &&
           NETSTACK_ROUTING.get_root_ipaddr(&dest_ipaddr)) {
          app_tx_count++;
          msg.src_id = node_id;
          msg.seq = app_tx_count;
          msg.tx_ticks = clock_time();
          LOG_INFO("PERF-TX src=%u seq=%lu tx_ticks=%lu\n",
                   msg.src_id, (unsigned long)msg.seq,
                   (unsigned long)msg.tx_ticks);
          simple_udp_sendto(&udp_conn, &msg, sizeof(msg), &dest_ipaddr);
        }
      }
      etimer_reset(&send_timer);
    }
  }

  PROCESS_END();
}
