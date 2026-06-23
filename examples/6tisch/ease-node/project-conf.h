#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_
#define IEEE802154_CONF_PANID 0x81a5
#define TSCH_CONF_AUTOSTART 0
#define SICSLOWPAN_CONF_FRAG 1
#define UIP_CONF_BUFFER_SIZE 240
#define EASE_PACKETS_PER_MIN 4
#define EASE_CONF_UNICAST_PERIOD 167
#define EASE_CONF_RDC_BUDGET_PCT 20
#define EASE_CONF_CUSUM_THRESHOLD 500
#define EASE_CONF_CUSUM_RHO 80
#define EASE_CONF_MAX_CHILDREN 30
#define EASE_CONF_WITH_GAME_THEORY 1
#define EASE_CONF_NUM_CHANNELS 16
#define ORCHESTRA_CONF_RULES { &eb_per_time_source, \
                               &ease_dedicated_cell, \
                               &ease_shared_cell, \
                               &default_common }
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
