#ifndef _NXT_APP_H_INCLUDED_
#define _NXT_APP_H_INCLUDED_


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


nxt_nsec_t nxt_app_latency_now(nxt_thread_t *thr);
void nxt_app_latency_record(nxt_app_latency_t *latency, nxt_nsec_t now,
    nxt_nsec_t duration);
nxt_bool_t nxt_app_latency_get(nxt_app_latency_t *latency, nxt_nsec_t now,
    uint64_t values[3]);


#endif /* _NXT_APP_H_INCLUDED_ */
