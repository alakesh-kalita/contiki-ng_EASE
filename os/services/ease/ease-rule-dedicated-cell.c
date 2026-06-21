/*
 * EASE dedicated cell rule.
 *
 * 1. Receiver-based shared cell: hash(EUI64(P)) — permanent until parent change.
 *    Parent always listens. Children contend via CSMA/CA.
 *
 * 2. When parent receives from child on shared cell → both allocate
 *    autonomous dedicated cell using hash(263*EUI64(P) + EUI64(C) + i).
 *
 * 3. CUSUM at parent increases the number of dedicated cells per child.
 *
 * 4. Game theory caps the upper limit of dedicated cells within RDC budget.
 */

#include "contiki.h"
#include "orchestra.h"
#include "ease.h"
#include "net/packetbuf.h"

#if UIP_MAX_ROUTES != 0

#include "net/ipv6/uip-ds6-route.h"

#include "sys/log.h"
#define LOG_MODULE "EASE-DC"
#define LOG_LEVEL  LOG_LEVEL_MAC

static uint16_t slotframe_handle = 0;
static struct tsch_slotframe *sf_ded;

/*--- Receiver-based cell: hash(addr) — permanent ---*/
static uint16_t
rcv_ts(const linkaddr_t *a)
{
  return EASE_DEDICATED_ZONE_START +
      (EASE_HASH((uint32_t)ORCHESTRA_LINKADDR_HASH(a))
       % EASE_DEDICATED_ZONE_SIZE);
}
static uint16_t
rcv_ch(const linkaddr_t *a)
{
  return (EASE_HASH((uint32_t)ORCHESTRA_LINKADDR_HASH(a) + EASE_CHANNEL_HASH_SEED)
       % (EASE_NUM_CHANNELS - 1)) + 1;
}

/*--- Pair-based dedicated cell: hash(263*P + C + i) ---*/
static uint16_t
ded_ts(const linkaddr_t *p, const linkaddr_t *c, uint16_t i)
{
  uint32_t h = EASE_HASH((uint32_t)ORCHESTRA_LINKADDR_HASH(p) * 263 +
                          (uint32_t)ORCHESTRA_LINKADDR_HASH(c));
  h = h ^ EASE_HASH((uint32_t)i + 1);
  return EASE_DEDICATED_ZONE_START +
      (((uint32_t)EASE_ALPHA_UP * h) % EASE_DEDICATED_ZONE_SIZE);
}
static uint16_t
ded_ch(const linkaddr_t *p, const linkaddr_t *c, uint16_t i)
{
  uint32_t h = EASE_HASH((uint32_t)ORCHESTRA_LINKADDR_HASH(p) * 263 +
                          (uint32_t)ORCHESTRA_LINKADDR_HASH(c) +
                          EASE_CHANNEL_HASH_SEED);
  h = h ^ EASE_HASH((uint32_t)i + 1);
  return (((uint32_t)EASE_ALPHA_UP * h) % (EASE_NUM_CHANNELS - 1)) + 1;
}

/*---------------------------------------------------------------------------*/
static int
neighbor_has_uc_link(const linkaddr_t *addr)
{
  if(addr == NULL || linkaddr_cmp(addr, &linkaddr_null)) return 0;
  if(linkaddr_cmp(&orchestra_parent_linkaddr, addr)) return 1;
  if(nbr_table_get_from_lladdr(nbr_routes, (linkaddr_t *)addr) != NULL) return 1;
  return 0;
}
/*---------------------------------------------------------------------------*/
/*
 * Add dedicated cells for a child. Called when CUSUM prediction increases.
 * Only ADDS — never removes existing cells.
 */
void
ease_add_dedicated_cells_for_child(const linkaddr_t *child_addr, uint16_t from_idx, uint16_t to_idx)
{
  uint16_t j;
  if(sf_ded == NULL) return;
  for(j = from_idx; j < to_idx; j++) {
    tsch_schedule_add_link(sf_ded, LINK_OPTION_RX,
        LINK_TYPE_NORMAL, &tsch_broadcast_address,
        ded_ts(&linkaddr_node_addr, child_addr, j),
        ded_ch(&linkaddr_node_addr, child_addr, j), 0);
  }
}
/*---------------------------------------------------------------------------*/
/*
 * Add dedicated TX cells toward parent. Called when self-prediction increases.
 */
void
ease_add_dedicated_tx_to_parent(uint16_t from_idx, uint16_t to_idx)
{
  uint16_t j;
  if(sf_ded == NULL) return;
  for(j = from_idx; j < to_idx; j++) {
    tsch_schedule_add_link(sf_ded, LINK_OPTION_TX,
        LINK_TYPE_NORMAL, &tsch_broadcast_address,
        ded_ts(&orchestra_parent_linkaddr, &linkaddr_node_addr, j),
        ded_ch(&orchestra_parent_linkaddr, &linkaddr_node_addr, j), 0);
  }
}
/*---------------------------------------------------------------------------*/
/* Called from ease_slotframe_update when CUSUM predictions change */
void
ease_update_dedicated_cells(void)
{
  int i;
  if(sf_ded == NULL) return;

  /* Parent side: add RX cells for children whose prediction increased */
  for(i = 0; i < EASE_MAX_CHILDREN; i++) {
    if(ease_children[i].in_use) {
      uint16_t need = ease_children[i].predicted;
      uint16_t have = ease_children[i].num_cells;
      if(need > have) {
        ease_add_dedicated_cells_for_child(&ease_children[i].addr, have, need);
        ease_children[i].num_cells = need;
      }
    }
  }

  /* Child side: add TX cells toward parent */
  {
    uint16_t need = ease_get_self_num_cells();
    static uint16_t self_have = 0;
    if(need > self_have) {
      ease_add_dedicated_tx_to_parent(self_have, need);
      self_have = need;
    }
  }
}
/*---------------------------------------------------------------------------*/
/* Full rebuild — only called on parent change or child remove.
 * Removes ALL links, re-adds shared cells + current dedicated cells. */
void
ease_rebuild_dedicated_schedule(void)
{
  int i;
  if(sf_ded == NULL) return;

  /* Remove all links */
  struct tsch_link *l = list_head(sf_ded->links_list);
  while(l != NULL) {
    struct tsch_link *next = list_item_next(l);
    tsch_schedule_remove_link(sf_ded, l);
    l = next;
  }

  /* Re-add permanent receiver-based shared RX cell */
  tsch_schedule_add_link(sf_ded, LINK_OPTION_RX,
      LINK_TYPE_NORMAL, &tsch_broadcast_address,
      rcv_ts(&linkaddr_node_addr), rcv_ch(&linkaddr_node_addr), 0);

  /* Re-add parent TX shared cell */
  if(!linkaddr_cmp(&orchestra_parent_linkaddr, &linkaddr_null)) {
    tsch_schedule_add_link(sf_ded,
        LINK_OPTION_TX | LINK_OPTION_SHARED,
        LINK_TYPE_NORMAL, &tsch_broadcast_address,
        rcv_ts(&orchestra_parent_linkaddr),
        rcv_ch(&orchestra_parent_linkaddr), 0);
  }

  /* Re-add existing dedicated cells for known children */
  for(i = 0; i < EASE_MAX_CHILDREN; i++) {
    if(ease_children[i].in_use && ease_children[i].num_cells > 0) {
      ease_add_dedicated_cells_for_child(&ease_children[i].addr,
                                          0, ease_children[i].num_cells);
    }
  }

  /* Re-add existing dedicated TX cells toward parent */
  {
    uint16_t self_nc = ease_get_self_num_cells();
    if(self_nc > 0) {
      ease_add_dedicated_tx_to_parent(0, self_nc);
    }
  }
}
/*---------------------------------------------------------------------------*/
static int
select_packet(uint16_t *slotframe, uint16_t *timeslot, uint16_t *channel_offset)
{
  const linkaddr_t *dest = packetbuf_addr(PACKETBUF_ADDR_RECEIVER);

  ease_check_slotframe_boundary();

  if(packetbuf_attr(PACKETBUF_ATTR_FRAME_TYPE) != FRAME802154_DATAFRAME) return 0;
  if(orchestra_is_root_schedule_active(dest)) return 0;
  if(!neighbor_has_uc_link(dest)) return 0;

  if(slotframe != NULL) *slotframe = slotframe_handle;

  /* After successful shared cell TX (fairness active) AND we have
   * dedicated cells → use dedicated cell. Otherwise → shared cell. */
  if(linkaddr_cmp(dest, &orchestra_parent_linkaddr)
     && ease_should_skip_shared_cell()
     && ease_get_self_num_cells() > 0) {
    if(timeslot != NULL)
      *timeslot = ded_ts(&orchestra_parent_linkaddr, &linkaddr_node_addr, 0);
    if(channel_offset != NULL)
      *channel_offset = ded_ch(&orchestra_parent_linkaddr, &linkaddr_node_addr, 0);
  } else {
    if(timeslot != NULL) *timeslot = rcv_ts(dest);
    if(channel_offset != NULL) *channel_offset = rcv_ch(dest);
  }

  return 1;
}
/*---------------------------------------------------------------------------*/
static void
new_time_source(const struct tsch_neighbor *old, const struct tsch_neighbor *new)
{
  if(new != old) {
    const linkaddr_t *old_addr = tsch_queue_get_nbr_address(old);
    const linkaddr_t *new_addr = tsch_queue_get_nbr_address(new);

    if(old_addr != NULL) tsch_queue_free_packets_to(old_addr);

    if(new_addr != NULL) {
      linkaddr_copy(&orchestra_parent_linkaddr, new_addr);
    } else {
      linkaddr_copy(&orchestra_parent_linkaddr, &linkaddr_null);
    }
    orchestra_parent_knows_us = 0;

    ease_rebuild_dedicated_schedule();
  }
}
/*---------------------------------------------------------------------------*/
static void
child_added(const linkaddr_t *addr)
{
  ease_add_child(addr);
  /* Don't rebuild — dedicated cells are added incrementally by CUSUM */
}
/*---------------------------------------------------------------------------*/
static void
child_removed(const linkaddr_t *addr)
{
  ease_remove_child(addr);
  tsch_queue_free_packets_to(addr);
  ease_rebuild_dedicated_schedule();
}
/*---------------------------------------------------------------------------*/
static void
init(uint16_t sf_handle)
{
  slotframe_handle = sf_handle;
  ease_init();
  sf_ded = tsch_schedule_add_slotframe(slotframe_handle, EASE_UNICAST_PERIOD);

  /* Permanent receiver-based shared RX cell */
  tsch_schedule_add_link(sf_ded, LINK_OPTION_RX,
      LINK_TYPE_NORMAL, &tsch_broadcast_address,
      rcv_ts(&linkaddr_node_addr), rcv_ch(&linkaddr_node_addr), 0);

  LOG_INFO("Init: sf=%u, own RX ts=%u ch=%u\n",
           slotframe_handle,
           rcv_ts(&linkaddr_node_addr),
           rcv_ch(&linkaddr_node_addr));
}
/*---------------------------------------------------------------------------*/
struct orchestra_rule ease_dedicated_cell = {
  init,
  new_time_source,
  select_packet,
  child_added,
  child_removed,
  NULL,
  NULL,
  "EASE dedicated cell",
  EASE_UNICAST_PERIOD,
};

#endif /* UIP_MAX_ROUTES */
