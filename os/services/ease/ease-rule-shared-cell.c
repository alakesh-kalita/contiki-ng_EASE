/*
 * Copyright (c) 2024, EASE Authors.
 * All rights reserved.
 *
 * EASE shared cell rule (Zone 1) — placeholder.
 * The actual shared cell (receiver-based) is handled in the dedicated
 * cell rule (Zone 2). This rule exists for Orchestra framework compatibility.
 */

#include "contiki.h"
#include "orchestra.h"
#include "ease.h"

#if UIP_MAX_ROUTES != 0

#include "net/ipv6/uip-ds6-route.h"

#include "sys/log.h"
#define LOG_MODULE "EASE-SH"
#define LOG_LEVEL  LOG_LEVEL_MAC

static uint16_t slotframe_handle = 0;
static struct tsch_slotframe *sf_shared;

/*---------------------------------------------------------------------------*/
static int
select_packet(uint16_t *slotframe, uint16_t *timeslot, uint16_t *channel_offset)
{
  return 0;
}
/*---------------------------------------------------------------------------*/
static void
new_time_source(const struct tsch_neighbor *old, const struct tsch_neighbor *new)
{
}
/*---------------------------------------------------------------------------*/
static void
child_added(const linkaddr_t *addr)
{
}
/*---------------------------------------------------------------------------*/
static void
child_removed(const linkaddr_t *addr)
{
}
/*---------------------------------------------------------------------------*/
static void
init(uint16_t sf_handle)
{
  slotframe_handle = sf_handle;
  sf_shared = tsch_schedule_add_slotframe(slotframe_handle, EASE_UNICAST_PERIOD);
  LOG_INFO("Shared cell rule init (placeholder): sf=%u\n", slotframe_handle);
}
/*---------------------------------------------------------------------------*/
struct orchestra_rule ease_shared_cell = {
  init,
  new_time_source,
  select_packet,
  child_added,
  child_removed,
  NULL,
  NULL,
  "EASE shared cell",
  EASE_UNICAST_PERIOD,
};

#endif /* UIP_MAX_ROUTES */
