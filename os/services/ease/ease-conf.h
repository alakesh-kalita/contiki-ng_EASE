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

/**
 * \file
 *         EASE configuration
 */

#ifndef EASE_CONF_H_
#define EASE_CONF_H_

/*---------------------------------------------------------------------------*/
/* Slotframe length for EASE unicast scheduling (shared + dedicated zones) */
#ifdef EASE_CONF_UNICAST_PERIOD
#define EASE_UNICAST_PERIOD              EASE_CONF_UNICAST_PERIOD
#else
#define EASE_UNICAST_PERIOD              101
#endif

/* Shared zone size: SFs = SF/2 (Zone 1 occupies first half) */
#ifdef EASE_CONF_SHARED_ZONE_SIZE
#define EASE_SHARED_ZONE_SIZE            EASE_CONF_SHARED_ZONE_SIZE
#else
#define EASE_SHARED_ZONE_SIZE            (EASE_UNICAST_PERIOD / 2)
#endif

/* Dedicated zone size: SFx = SF - SFs - 1 (Zone 2 starts at SFs+1, ends at SF-1) */
#define EASE_DEDICATED_ZONE_SIZE         (EASE_UNICAST_PERIOD - EASE_SHARED_ZONE_SIZE - 1)

/* Dedicated zone start offset: SFs + 1 (per paper Section B) */
#define EASE_DEDICATED_ZONE_START        (EASE_SHARED_ZONE_SIZE + 1)

/*---------------------------------------------------------------------------*/
/* RDC budget: duty-cycle constraint delta as percentage, 0-100
 * B = floor(delta * SF) = floor(EASE_RDC_BUDGET_PCT/100 * EASE_UNICAST_PERIOD) */
#ifdef EASE_CONF_RDC_BUDGET_PCT
#define EASE_RDC_BUDGET_PCT              EASE_CONF_RDC_BUDGET_PCT
#else
#define EASE_RDC_BUDGET_PCT              20
#endif

/*---------------------------------------------------------------------------*/
/* CUSUM predictor parameters (Equations 2-5) */

/* CUSUM threshold H: scaled x100. H=500 means actual threshold 5.0 */
#ifdef EASE_CONF_CUSUM_THRESHOLD
#define EASE_CUSUM_THRESHOLD             EASE_CONF_CUSUM_THRESHOLD
#else
#define EASE_CUSUM_THRESHOLD             500
#endif

/* CUSUM tracking coefficient rho: scaled x100. rho=80 means 0.80 */
#ifdef EASE_CONF_CUSUM_RHO
#define EASE_CUSUM_RHO                   EASE_CONF_CUSUM_RHO
#else
#define EASE_CUSUM_RHO                   80
#endif

/*---------------------------------------------------------------------------*/
/* Game-theoretic parameters (Equations 6-16) */

/* Maximum number of children per parent */
#ifdef EASE_CONF_MAX_CHILDREN
#define EASE_MAX_CHILDREN                EASE_CONF_MAX_CHILDREN
#else
#define EASE_MAX_CHILDREN                10
#endif

/* Default priority weight w_i for a child node (integer, e.g. 1,2,3,4).
 * Higher weight = higher priority. Paper example: w=(4,3,2,1). */
#ifdef EASE_CONF_DEFAULT_WEIGHT
#define EASE_DEFAULT_WEIGHT              EASE_CONF_DEFAULT_WEIGHT
#else
#define EASE_DEFAULT_WEIGHT              1
#endif

/* Minimum cells per child: k_min_i (Eq. 8) */
#ifdef EASE_CONF_MIN_CELLS_PER_CHILD
#define EASE_MIN_CELLS_PER_CHILD         EASE_CONF_MIN_CELLS_PER_CHILD
#else
#define EASE_MIN_CELLS_PER_CHILD         0
#endif

/* Maximum cells per child: k_max_i (Eq. 8) */
#ifdef EASE_CONF_MAX_CELLS_PER_CHILD
#define EASE_MAX_CELLS_PER_CHILD         EASE_CONF_MAX_CELLS_PER_CHILD
#else
#define EASE_MAX_CELLS_PER_CHILD         10
#endif

/* Number of bisection iterations for solving lambda* (Eq. 15) */
#ifdef EASE_CONF_BISECTION_ITERATIONS
#define EASE_BISECTION_ITERATIONS        EASE_CONF_BISECTION_ITERATIONS
#else
#define EASE_BISECTION_ITERATIONS        16
#endif

/* Fixed-point scale for lambda in bisection (integer precision) */
#define EASE_LAMBDA_SCALE                1000

/*---------------------------------------------------------------------------*/
/* Direction multiplier alpha for dedicated cell hashing (Section I)
 * alpha distinguishes upward vs downward traffic so they don't collide */

#ifdef EASE_CONF_ALPHA_UP
#define EASE_ALPHA_UP                    EASE_CONF_ALPHA_UP
#else
#define EASE_ALPHA_UP                    1
#endif

#ifdef EASE_CONF_ALPHA_DOWN
#define EASE_ALPHA_DOWN                  EASE_CONF_ALPHA_DOWN
#else
#define EASE_ALPHA_DOWN                  2
#endif

/*---------------------------------------------------------------------------*/
/* Enable/disable game-theoretic allocation (if disabled, use CUSUM only) */
#ifdef EASE_CONF_WITH_GAME_THEORY
#define EASE_WITH_GAME_THEORY            EASE_CONF_WITH_GAME_THEORY
#else
#define EASE_WITH_GAME_THEORY            1
#endif

/* Number of available channels Nc for channel offset computation */
#ifdef EASE_CONF_NUM_CHANNELS
#define EASE_NUM_CHANNELS                EASE_CONF_NUM_CHANNELS
#else
#define EASE_NUM_CHANNELS                16
#endif

/*---------------------------------------------------------------------------*/
/* Hash function: Knuth multiplicative hash for pseudo-random cell placement */
#ifdef EASE_CONF_HASH
#define EASE_HASH                        EASE_CONF_HASH
#else
#define EASE_HASH(x)                     ((uint32_t)(x) * 2654435761UL)
#endif

/* Seed to decorrelate channel offset hash from timeslot hash */
#define EASE_CHANNEL_HASH_SEED           0x9E3779B9UL

#endif /* EASE_CONF_H_ */
