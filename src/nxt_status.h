
/*
 * Copyright (C) NGINX, Inc.
 */

#ifndef _NXT_STATUS_H_INCLUDED_
#define _NXT_STATUS_H_INCLUDED_


typedef struct {
    nxt_str_t         name;
    uint64_t          total_requests;
    uint64_t          responses[5];
    uint32_t          waiting_requests;
    uint32_t          processing_requests;
    uint32_t          pending_processes;
    uint32_t          processes;
    uint32_t          idle_processes;
    uint32_t          stopping_processes;
} nxt_status_app_t;


typedef struct {
    uint64_t          requests;

    size_t            apps_count;
    nxt_status_app_t  apps[];
} nxt_status_report_t;


nxt_conf_value_t *nxt_status_get(nxt_status_report_t *report, nxt_mp_t *mp);


#endif /* _NXT_STATUS_H_INCLUDED_ */
