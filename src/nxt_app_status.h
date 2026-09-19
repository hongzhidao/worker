
/*
 * Copyright (C) NGINX, Inc.
 */

#ifndef _NXT_APP_STATUS_H_INCLUDED_
#define _NXT_APP_STATUS_H_INCLUDED_


#include <nxt_conf.h>


#define NXT_APP_LATENCY_WINDOW   60
/* 16 sub-buckets per power of two cover nanoseconds converted to ms. */
#define NXT_APP_LATENCY_BUCKETS  672


typedef struct {
    uint64_t  second;
    uint64_t  buckets[NXT_APP_LATENCY_BUCKETS];
} nxt_app_latency_slice_t;


typedef struct {
    nxt_app_latency_slice_t  slices[NXT_APP_LATENCY_WINDOW];
} nxt_app_latency_t;


/* Raw statistics owned by an app and protected by app->mutex. */
typedef struct {
    uint64_t           total_requests;
    uint64_t           responses[5];
    nxt_app_latency_t  *latency;
} nxt_app_status_t;


typedef struct {
    nxt_str_t         name;
    uint64_t          total_requests;
    uint64_t          responses[5];
    uint64_t          latency[3];
    nxt_bool_t        latency_valid;
    uint64_t          waiting_requests;
    uint64_t          processing_requests;
    uint64_t          pending_processes;
    uint64_t          processes;
    uint64_t          idle_processes;
    uint64_t          stopping_processes;
} nxt_app_status_info_t;


typedef struct {
    nxt_app_status_info_t  summary;

    size_t                apps_count;
    nxt_app_status_info_t  apps[];
} nxt_app_status_report_t;


nxt_nsec_t nxt_app_latency_now(nxt_thread_t *thr);
void nxt_app_latency_record(nxt_app_latency_t *latency, nxt_nsec_t now,
    nxt_nsec_t duration);
nxt_bool_t nxt_app_latency_get(const nxt_app_latency_t *latency, nxt_nsec_t now,
    uint64_t values[3]);
void nxt_app_latency_merge(uint64_t buckets[NXT_APP_LATENCY_BUCKETS],
    const nxt_app_latency_t *latency, nxt_nsec_t now);
nxt_bool_t nxt_app_latency_percentiles(
    const uint64_t buckets[NXT_APP_LATENCY_BUCKETS], uint64_t values[3]);

/* The caller must hold the owning app's mutex when updating statistics. */
void nxt_app_status_record_latency(nxt_app_status_t *status, nxt_thread_t *thr,
    nxt_nsec_t processing_start);
void nxt_app_status_response(nxt_app_status_t *status, nxt_uint_t code);
/* Collect on the thread that owns these queues. */
nxt_buf_t *nxt_app_status_report(nxt_task_t *task, nxt_mp_t *mp,
    nxt_queue_t *apps, nxt_queue_t *stopping_processes);
nxt_conf_value_t *nxt_app_status_get(nxt_app_status_report_t *report,
    nxt_mp_t *mp);


#endif /* _NXT_APP_STATUS_H_INCLUDED_ */
