/*
 * EASE core: CUSUM predictor + game-theoretic cap.
 *
 * CUSUM runs at each slotframe boundary. When prediction increases,
 * ease_update_dedicated_cells adds cells incrementally (never removes).
 * Game theory caps predictions within the RDC budget.
 */

#include "contiki.h"
#include "ease.h"
#include "net/mac/tsch/tsch.h"
#include "net/mac/tsch/tsch-schedule.h"

#include "sys/log.h"
#define LOG_MODULE "EASE"
#define LOG_LEVEL  LOG_LEVEL_MAC

/*---------------------------------------------------------------------------*/
struct ease_child_state ease_children[EASE_MAX_CHILDREN];
uint16_t ease_num_children = 0;

static uint8_t shared_tx_last_sf = 0;
static uint8_t shared_tx_this_sf = 0;
static uint16_t self_predicted = 0;
static uint16_t self_pkts_this_sf = 0;
static uint32_t last_asfn = 0;

/*---------------------------------------------------------------------------*/
void
ease_init(void)
{
  int i;
  for(i = 0; i < EASE_MAX_CHILDREN; i++) {
    ease_children[i].in_use = 0;
    ease_children[i].mu = 0;
    ease_children[i].cusum_s = 0;
    ease_children[i].predicted = 0;
    ease_children[i].num_cells = 0;
    ease_children[i].quota = 0;
    ease_children[i].tokens = 1;
    ease_children[i].pkts_this_sf = 0;
  }
  ease_num_children = 0;
  shared_tx_last_sf = 0;
  shared_tx_this_sf = 0;
  self_predicted = 0;
  self_pkts_this_sf = 0;
  last_asfn = 0;
}
/*---------------------------------------------------------------------------*/
struct ease_child_state *
ease_find_child(const linkaddr_t *addr)
{
  int i;
  if(addr == NULL) return NULL;
  for(i = 0; i < EASE_MAX_CHILDREN; i++) {
    if(ease_children[i].in_use && linkaddr_cmp(&ease_children[i].addr, addr))
      return &ease_children[i];
  }
  return NULL;
}
/*---------------------------------------------------------------------------*/
struct ease_child_state *
ease_add_child(const linkaddr_t *addr)
{
  int i;
  if(addr == NULL) return NULL;
  struct ease_child_state *c = ease_find_child(addr);
  if(c != NULL) return c;

  for(i = 0; i < EASE_MAX_CHILDREN; i++) {
    if(!ease_children[i].in_use) {
      ease_children[i].in_use = 1;
      linkaddr_copy(&ease_children[i].addr, addr);
      ease_children[i].mu = 0;
      ease_children[i].cusum_s = 0;
      ease_children[i].predicted = 0;
      ease_children[i].num_cells = 0;
      ease_children[i].quota = 0;
      ease_children[i].tokens = 1;
      ease_children[i].pkts_this_sf = 0;
      ease_num_children++;
      return &ease_children[i];
    }
  }
  return NULL;
}
/*---------------------------------------------------------------------------*/
void
ease_remove_child(const linkaddr_t *addr)
{
  struct ease_child_state *c = ease_find_child(addr);
  if(c != NULL) {
    c->in_use = 0;
    if(ease_num_children > 0) ease_num_children--;
  }
}
/*---------------------------------------------------------------------------*/
/* CUSUM (Eq. 2-5). Utilization-aware: adj = D_t+1 when saturated. */
void
ease_cusum_update(struct ease_child_state *child, uint16_t D_t)
{
  uint16_t nc = (child->predicted > 0) ? child->predicted : 1;
  uint16_t adj = D_t;
  if(adj >= nc) adj = D_t + 1;

  int32_t dt = (int32_t)adj * 100;
  int32_t z = dt - child->mu;
  int32_t s = child->cusum_s + z;
  if(s < 0) s = 0;
  child->cusum_s = s;

  if(s > (int32_t)EASE_CUSUM_THRESHOLD) {
    child->mu = dt;
    child->cusum_s = 0;
  } else {
    child->mu = ((int32_t)EASE_CUSUM_RHO * child->mu +
                 (100 - (int32_t)EASE_CUSUM_RHO) * dt) / 100;
  }

  child->predicted = (child->mu > 0)
                     ? (uint16_t)((child->mu + 99) / 100) : 0;

  LOG_INFO("CUSUM ");
  LOG_INFO_LLADDR(&child->addr);
  LOG_INFO_(": D_t=%u, adj=%u, cells=%u, pred=%u\n",
            D_t, adj, nc, child->predicted);
}
/*---------------------------------------------------------------------------*/
void
ease_slotframe_update(void)
{
  int i;

  /* 1. CUSUM on each child's received traffic */
  for(i = 0; i < EASE_MAX_CHILDREN; i++) {
    if(ease_children[i].in_use) {
      ease_cusum_update(&ease_children[i], ease_children[i].pkts_this_sf);
      ease_children[i].pkts_this_sf = 0;
    }
  }

  /* 2. Self-CUSUM (child side — mirrors parent's prediction) */
  {
    uint16_t nc = (self_predicted > 0) ? self_predicted : 1;
    uint16_t adj = self_pkts_this_sf;
    if(adj >= nc) adj = self_pkts_this_sf + 1;
    int32_t dt = (int32_t)adj * 100;
    static int32_t smu = 0, scs = 0;
    int32_t z = dt - smu;
    int32_t s = scs + z;
    if(s < 0) s = 0;
    scs = s;
    if(s > (int32_t)EASE_CUSUM_THRESHOLD) {
      smu = dt; scs = 0;
    } else {
      smu = ((int32_t)EASE_CUSUM_RHO * smu +
             (100 - (int32_t)EASE_CUSUM_RHO) * dt) / 100;
    }
    self_predicted = (smu > 0) ? (uint16_t)((smu + 99) / 100) : 0;
    self_pkts_this_sf = 0;
  }

  /* 3. Fairness tracking */
  shared_tx_last_sf = shared_tx_this_sf;
  shared_tx_this_sf = 0;

  /* 4. Game theory: cap predictions within RDC budget */
#if EASE_WITH_GAME_THEORY
  {
    uint16_t B = (EASE_RDC_BUDGET_PCT * EASE_UNICAST_PERIOD) / 100;
    uint32_t sw = 0;
    for(i = 0; i < EASE_MAX_CHILDREN; i++)
      if(ease_children[i].in_use) sw += EASE_DEFAULT_WEIGHT;

    if(ease_num_children > 0 && B > 0 && sw > 0) {
      uint32_t lo = 1, hi = sw * EASE_LAMBDA_SCALE, mid;
      int iter;
      for(iter = 0; iter < EASE_BISECTION_ITERATIONS; iter++) {
        mid = (lo + hi) / 2;
        if(mid == 0) mid = 1;
        int32_t d = 0;
        for(i = 0; i < EASE_MAX_CHILDREN; i++) {
          if(ease_children[i].in_use) {
            int32_t k = ((int32_t)EASE_DEFAULT_WEIGHT * EASE_LAMBDA_SCALE)
                        / (int32_t)mid - 1;
            if(k < 0) k = 0;
            if(k > (int32_t)EASE_MAX_CELLS_PER_CHILD) k = EASE_MAX_CELLS_PER_CHILD;
            d += k;
          }
        }
        if(d > (int32_t)B) lo = mid; else hi = mid;
      }
      mid = (lo + hi) / 2;
      if(mid == 0) mid = 1;

      for(i = 0; i < EASE_MAX_CHILDREN; i++) {
        if(ease_children[i].in_use) {
          int32_t k = ((int32_t)EASE_DEFAULT_WEIGHT * EASE_LAMBDA_SCALE)
                      / (int32_t)mid - 1;
          if(k < 0) k = 0;
          if(k > (int32_t)EASE_MAX_CELLS_PER_CHILD) k = EASE_MAX_CELLS_PER_CHILD;
          ease_children[i].quota = (uint16_t)k;
          /* Cap: prediction cannot exceed quota */
          if(ease_children[i].predicted > ease_children[i].quota) {
            ease_children[i].predicted = ease_children[i].quota;
          }
        }
      }
    }
  }
#endif

  /* 5. Token bucket init (Eq. 17) */
#if EASE_WITH_GAME_THEORY
  {
    uint32_t total_q = 0;
    for(i = 0; i < EASE_MAX_CHILDREN; i++)
      if(ease_children[i].in_use) total_q += ease_children[i].quota;

    uint16_t B = (EASE_RDC_BUDGET_PCT * EASE_UNICAST_PERIOD) / 100;
    for(i = 0; i < EASE_MAX_CHILDREN; i++) {
      if(ease_children[i].in_use) {
        uint16_t q = ease_children[i].quota;
        uint16_t p = ease_children[i].predicted;
        if(total_q <= B) {
          ease_children[i].tokens = (q > p) ? q : p;
        } else {
          ease_children[i].tokens = (q < p) ? q : p;
        }
        if(ease_children[i].tokens == 0) {
          ease_children[i].tokens = 1;
        }
      }
    }
  }
#endif

  /* 6. Incrementally add dedicated cells where predictions increased */
  ease_update_dedicated_cells();
}
/*---------------------------------------------------------------------------*/
void
ease_check_slotframe_boundary(void)
{
  uint32_t cur = ease_get_asfn();
  if(cur != last_asfn && last_asfn != 0) {
    ease_slotframe_update();
  }
  last_asfn = cur;
}
/*---------------------------------------------------------------------------*/
void
ease_notify_rx(const linkaddr_t *child_addr)
{
  struct ease_child_state *c;
  if(child_addr == NULL) return;
  c = ease_find_child(child_addr);
  if(c == NULL) {
    c = ease_add_child(child_addr);
    if(c == NULL) return;
  }
  c->pkts_this_sf++;
#if EASE_WITH_GAME_THEORY
  if(c->tokens > 0) c->tokens--;
#endif
}
/*---------------------------------------------------------------------------*/
void ease_notify_tx(void) { self_pkts_this_sf++; }
void ease_notify_shared_tx_success(void) { shared_tx_this_sf = 1; }
int  ease_should_skip_shared_cell(void) { return shared_tx_last_sf; }
/*---------------------------------------------------------------------------*/
uint16_t
ease_get_num_dedicated_cells(const linkaddr_t *child_addr)
{
  struct ease_child_state *c = ease_find_child(child_addr);
  return (c != NULL) ? c->predicted : 0;
}
/*---------------------------------------------------------------------------*/
uint16_t ease_get_self_num_cells(void) { return self_predicted; }
uint32_t ease_get_asfn(void) { return tsch_current_asn.ls4b / EASE_UNICAST_PERIOD; }
/*---------------------------------------------------------------------------*/
int
ease_do_nack(struct tsch_link *link, linkaddr_t *src, linkaddr_t *dst)
{
#if EASE_WITH_GAME_THEORY
  struct ease_child_state *c;
  if(src == NULL) return 0;
  c = ease_find_child(src);
  if(c == NULL) return 0;
  if(c->tokens == 0) return 1;
#endif
  return 0;
}
