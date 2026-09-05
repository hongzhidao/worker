
/*
 * Copyright (C) Igor Sysoev
 * Copyright (C) NGINX, Inc.
 */

#include <nxt_router.h>
#include <nxt_http.h>


static nxt_int_t nxt_http_action_resolve(nxt_task_t *task,
    nxt_router_temp_conf_t *tmcf, nxt_http_action_t *action);
static nxt_http_action_t *nxt_http_pass_var(nxt_task_t *task,
    nxt_http_request_t *r, nxt_http_action_t *action);
static void nxt_http_pass_query(nxt_task_t *task, nxt_http_request_t *r,
    nxt_http_action_t *action);
static nxt_int_t nxt_http_pass_find(nxt_mp_t *mp, nxt_router_conf_t *rtcf,
    nxt_str_t *pass, nxt_http_action_t *action);


static nxt_int_t
nxt_http_action_resolve(nxt_task_t *task, nxt_router_temp_conf_t *tmcf,
    nxt_http_action_t *action)
{
    nxt_int_t  ret;
    nxt_str_t  pass;

    if (action->handler != NULL) {
        return NXT_OK;
    }

    if (nxt_tstr_is_const(action->u.tstr)) {
        nxt_tstr_str(action->u.tstr, &pass);

        ret = nxt_http_pass_find(tmcf->router_conf->mem_pool,
                                 tmcf->router_conf, &pass, action);
        if (nxt_slow_path(ret != NXT_OK)) {
            return NXT_ERROR;
        }

    } else {
        action->handler = nxt_http_pass_var;
    }

    return NXT_OK;
}


static nxt_http_action_t *
nxt_http_pass_var(nxt_task_t *task, nxt_http_request_t *r,
    nxt_http_action_t *action)
{
    nxt_int_t          ret;
    nxt_str_t          str;
    nxt_tstr_t         *tstr;
    nxt_router_conf_t  *rtcf;

    tstr = action->u.tstr;

    nxt_tstr_str(tstr, &str);

    nxt_debug(task, "http pass: \"%V\"", &str);

    rtcf = r->conf->socket_conf->router_conf;

    ret = nxt_tstr_query_init(&r->tstr_query, rtcf->tstr_state, &r->tstr_cache,
                              r, r->mem_pool);
    if (nxt_slow_path(ret != NXT_OK)) {
        goto fail;
    }

    action = nxt_mp_zget(r->mem_pool,
                         sizeof(nxt_http_action_t) + sizeof(nxt_str_t));
    if (nxt_slow_path(action == NULL)) {
        goto fail;
    }

    action->u.pass = nxt_pointer_to(action, sizeof(nxt_http_action_t));

    ret = nxt_tstr_query(task, r->tstr_query, tstr, action->u.pass);
    if (nxt_slow_path(ret != NXT_OK)) {
        goto fail;
    }

    nxt_http_pass_query(task, r, action);

    return NULL;

fail:

    nxt_http_request_error(task, r, NXT_HTTP_INTERNAL_SERVER_ERROR);
    return NULL;
}


static void
nxt_http_pass_query(nxt_task_t *task, nxt_http_request_t *r,
    nxt_http_action_t *action)
{
    nxt_int_t          ret;
    nxt_router_conf_t  *rtcf;
    nxt_http_status_t  status;

    rtcf = r->conf->socket_conf->router_conf;

    nxt_debug(task, "http pass lookup: %V", action->u.pass);

    ret = nxt_http_pass_find(r->mem_pool, rtcf, action->u.pass, action);

    if (ret != NXT_OK) {
        status = (ret == NXT_DECLINED) ? NXT_HTTP_NOT_FOUND
                                       : NXT_HTTP_INTERNAL_SERVER_ERROR;

        nxt_http_request_error(task, r, status);
        return;
    }

    nxt_http_request_action(task, r, action);
}


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

    action->u.tstr = nxt_tstr_compile(rtcf->tstr_state, pass, 0);
    if (nxt_slow_path(action->u.tstr == NULL)) {
        return NULL;
    }

    action->handler = NULL;

    ret = nxt_http_action_resolve(task, tmcf, action);
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
