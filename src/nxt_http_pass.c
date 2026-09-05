
/*
 * Copyright (C) Igor Sysoev
 * Copyright (C) NGINX, Inc.
 */

#include <nxt_router.h>
#include <nxt_http.h>


static nxt_int_t
nxt_http_pass_find(nxt_mp_t *mp, nxt_router_conf_t *rtcf, nxt_str_t *pass,
    nxt_http_action_t *action)
{
    nxt_int_t  ret;
    nxt_str_t  segments[3];

    ret = nxt_http_pass_segments(mp, pass, segments, 3);
    if (nxt_slow_path(ret != NXT_OK)) {
        return ret;
    }

    if (nxt_str_eq(&segments[0], "applications", 12)) {
        return nxt_router_application_init(mp, rtcf, &segments[1],
                                           &segments[2], action);
    }

    return NXT_DECLINED;
}


nxt_int_t
nxt_http_pass_segments(nxt_mp_t *mp, nxt_str_t *pass, nxt_str_t *segments,
    nxt_uint_t n)
{
    u_char     *p;
    nxt_str_t  rest;

    if (nxt_slow_path(nxt_str_dup(mp, &rest, pass) == NULL)) {
        return NXT_ERROR;
    }

    nxt_memzero(segments, n * sizeof(nxt_str_t));

    do {
        p = nxt_memchr(rest.start, '/', rest.length);

        if (p != NULL) {
            n--;

            if (n == 0) {
                return NXT_DECLINED;
            }

            segments->length = p - rest.start;
            segments->start = rest.start;

            rest.length -= segments->length + 1;
            rest.start = p + 1;

        } else {
            n = 0;
            *segments = rest;
        }

        if (segments->length == 0) {
            return NXT_DECLINED;
        }

        p = nxt_decode_uri(segments->start, segments->start, segments->length);
        if (p == NULL) {
            return NXT_DECLINED;
        }

        segments->length = p - segments->start;
        segments++;

    } while (n);

    return NXT_OK;
}


nxt_http_action_t *
nxt_http_action_create(nxt_task_t *task, nxt_router_temp_conf_t *tmcf,
    nxt_str_t *pass)
{
    nxt_mp_t           *mp;
    nxt_int_t          ret;
    nxt_router_conf_t  *rtcf;
    nxt_http_action_t  *action;

    rtcf = tmcf->router_conf;
    mp = rtcf->mem_pool;

    action = nxt_mp_zalloc(mp, sizeof(nxt_http_action_t));
    if (nxt_slow_path(action == NULL)) {
        return NULL;
    }

    ret = nxt_http_pass_find(mp, rtcf, pass, action);
    if (nxt_slow_path(ret != NXT_OK)) {
        return NULL;
    }

    return action;
}


/* COMPATIBILITY: listener application. */

nxt_http_action_t *
nxt_http_pass_application(nxt_task_t *task, nxt_router_conf_t *rtcf,
    nxt_str_t *name)
{
    nxt_http_action_t  *action;

    action = nxt_mp_zalloc(rtcf->mem_pool, sizeof(nxt_http_action_t));
    if (nxt_slow_path(action == NULL)) {
        return NULL;
    }

    (void) nxt_router_application_init(rtcf->mem_pool, rtcf, name, NULL, action);

    return action;
}
