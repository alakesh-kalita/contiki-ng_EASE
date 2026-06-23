/*
 * Copyright (c) 2024, EASE Authors.
 * All rights reserved.
 */

#ifndef EASE_H_
#define EASE_H_

#include "net/mac/tsch/tsch.h"
#include "net/linkaddr.h"
#include "orchestra.h"
#include "ease-conf.h"

/*---------------------------------------------------------------------------*/
/* Per-child state maintained by the parent node */
struct ease_child_state {
  linkaddr_t addr;
  uint8_t in_use;

  /* CUSUM predictor state (mu and cusum_s are scaled x100) */
  int32_t mu;
  int32_t cusum_s;
  uint16_t predicted;     /* c_{t+1}: dedicated cells to allocate */

  /* Game theory allocation */
  uint16_t quota;         /* q_i from NE solution */
  uint16_t tokens;        /* token bucket counter */

  /* Current allocated dedicated cells (for change detection) */
  uint16_t num_cells;

  /* Traffic tracking per slotframe */
  uint16_t pkts_this_sf;
};

/*---------------------------------------------------------------------------*/
/* EASE global state */
extern struct ease_child_state ease_children[EASE_MAX_CHILDREN];
extern uint16_t ease_num_children;

/*---------------------------------------------------------------------------*/
/* Core functions */
void ease_init(void);
struct ease_child_state *ease_add_child(const linkaddr_t *addr);
void ease_remove_child(const linkaddr_t *addr);
struct ease_child_state *ease_find_child(const linkaddr_t *addr);

/* Called at each slotframe boundary: runs CUSUM, rebuilds dedicated cells */
void ease_slotframe_update(void);
void ease_check_slotframe_boundary(void);

/* CUSUM predictor (Eq. 2-5) */
void ease_cusum_update(struct ease_child_state *child, uint16_t observed_demand);

/* Packet tracking */
void ease_notify_rx(const linkaddr_t *child_addr);
void ease_notify_tx(void);

/* Fairness: skip shared cell after successful TX */
void ease_notify_shared_tx_success(void);
int ease_should_skip_shared_cell(void);

/* Cell count */
uint16_t ease_get_num_dedicated_cells(const linkaddr_t *child_addr);
uint16_t ease_get_self_num_cells(void);

/* ASFN */
uint32_t ease_get_asfn(void);

/* Budget-exhausted indication piggybacked in enhanced ACK (parent side) */
int ease_do_nack(struct tsch_link *link, linkaddr_t *src, linkaddr_t *dst);

/* Budget-exhausted indication received in enhanced ACK (child side) */
void ease_notify_budget_exhausted(void);
int ease_is_budget_exhausted(void);

/* Schedule management */
void ease_rebuild_dedicated_schedule(void);
void ease_update_dedicated_cells(void);

/*---------------------------------------------------------------------------*/
/* Orchestra rule declarations */
extern struct orchestra_rule ease_shared_cell;
extern struct orchestra_rule ease_dedicated_cell;

#endif /* EASE_H_ */
