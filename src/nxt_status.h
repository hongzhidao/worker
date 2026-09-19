
/*
 * Copyright (C) NGINX, Inc.
 */

#ifndef _NXT_STATUS_H_INCLUDED_
#define _NXT_STATUS_H_INCLUDED_


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
} nxt_status_app_t;


typedef struct {
    nxt_status_app_t  summary;

    size_t            apps_count;
    nxt_status_app_t  apps[];
} nxt_status_report_t;


nxt_conf_value_t *nxt_status_get(nxt_status_report_t *report, nxt_mp_t *mp);


#endif /* _NXT_STATUS_H_INCLUDED_ */
