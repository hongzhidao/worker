
/*
 * Copyright (C) Igor Sysoev
 * Copyright (C) NGINX, Inc.
 */

#include <nxt_router.h>
#include <nxt_http.h>


nxt_http_action_t *
nxt_http_pass_application(nxt_task_t *task, nxt_router_conf_t *rtcf,
    nxt_str_t *name, nxt_str_t *target)
{
    nxt_int_t          ret;
    nxt_http_action_t  *action;

    action = nxt_mp_zalloc(rtcf->mem_pool, sizeof(nxt_http_action_t));
    if (nxt_slow_path(action == NULL)) {
        return NULL;
    }

    ret = nxt_router_application_init(rtcf->mem_pool, rtcf, name, target, action);
    if (nxt_slow_path(ret != NXT_OK)) {
        return NULL;
    }

    return action;
}
