
/*
 * Copyright (C) NGINX, Inc.
 */

#include <nxt_main.h>
#include <nxt_router.h>
#include <nxt_http.h>
#include <nxt_app_status.h>


nxt_nsec_t
nxt_app_latency_now(nxt_thread_t *thr)
{
#if (NXT_HAVE_CLOCK_MONOTONIC)
    struct timespec  ts;

    /* Measure elapsed time before rounding; the cached clock is too coarse. */
    (void) clock_gettime(CLOCK_MONOTONIC, &ts);

    return (nxt_nsec_t) ts.tv_sec * 1000000000 + ts.tv_nsec;
#else
    nxt_thread_time_update(thr);
    return nxt_thread_monotonic_time(thr);
#endif
}


void
nxt_app_latency_record(nxt_app_latency_t *latency, nxt_nsec_t now,
    nxt_nsec_t duration)
{
    uint64_t                 second, msec;
    nxt_uint_t               bucket;
    nxt_app_latency_slice_t  *slice;

    second = now / 1000000000;
    slice = &latency->slices[second % NXT_APP_LATENCY_WINDOW];

    if (slice->second > second) {
        return;
    }

    if (slice->second != second) {
        nxt_memzero(slice, sizeof(*slice));
        slice->second = second;
    }

    msec = duration / 1000000;
    bucket = 0;

    /* Exact integer milliseconds below 32; wider buckets above that. */
    while (msec >= 32) {
        msec >>= 1;
        bucket += 16;
    }

    bucket += msec;
    nxt_assert(bucket < NXT_APP_LATENCY_BUCKETS);
    slice->buckets[bucket]++;
}


nxt_bool_t
nxt_app_latency_get(const nxt_app_latency_t *latency, nxt_nsec_t now,
    uint64_t values[3])
{
    uint64_t  buckets[NXT_APP_LATENCY_BUCKETS];

    nxt_memzero(buckets, sizeof(buckets));
    nxt_app_latency_merge(buckets, latency, now);

    return nxt_app_latency_percentiles(buckets, values);
}


void
nxt_app_latency_merge(uint64_t buckets[NXT_APP_LATENCY_BUCKETS],
    const nxt_app_latency_t *latency, nxt_nsec_t now)
{
    uint64_t                       second;
    nxt_uint_t                     i, j;
    const nxt_app_latency_slice_t  *slice;

    if (latency == NULL) {
        return;
    }

    second = now / 1000000000;

    for (i = 0; i < NXT_APP_LATENCY_WINDOW; i++) {
        slice = &latency->slices[i];

        if (slice->second > second
            || second - slice->second >= NXT_APP_LATENCY_WINDOW)
        {
            continue;
        }

        for (j = 0; j < NXT_APP_LATENCY_BUCKETS; j++) {
            buckets[j] += slice->buckets[j];
        }
    }
}


nxt_bool_t
nxt_app_latency_percentiles(const uint64_t buckets[NXT_APP_LATENCY_BUCKETS],
    uint64_t values[3])
{
    uint64_t    count, cumulative, ranks[3];
    nxt_uint_t  i, quantile, shift;

    static const uint8_t  percentages[] = { 50, 95, 99 };

    nxt_memzero(values, 3 * sizeof(uint64_t));

    count = 0;

    for (i = 0; i < NXT_APP_LATENCY_BUCKETS; i++) {
        count += buckets[i];
    }

    if (count == 0) {
        return 0;
    }

    for (i = 0; i < nxt_nitems(percentages); i++) {
        /* Nearest rank, without overflowing count * percentage. */
        ranks[i] = count / 100 * percentages[i]
                   + (count % 100 * percentages[i] + 99) / 100;
    }

    cumulative = 0;
    quantile = 0;

    for (i = 0; i < NXT_APP_LATENCY_BUCKETS; i++) {
        cumulative += buckets[i];

        while (cumulative >= ranks[quantile]) {
            if (i < 16) {
                values[quantile] = i;

            } else {
                shift = i / 16 - 1;
                values[quantile] = ((uint64_t) (i % 16 + 17) << shift) - 1;
            }

            if (++quantile == nxt_nitems(percentages)) {
                return 1;
            }
        }
    }

    return 0;
}


void
nxt_app_status_record_latency(nxt_app_status_t *status, nxt_thread_t *thr,
    nxt_nsec_t processing_start)
{
    nxt_nsec_t  now;

    now = nxt_app_latency_now(thr);

    if (status->latency == NULL) {
        status->latency = nxt_zalloc(sizeof(nxt_app_latency_t));
    }

    if (status->latency != NULL) {
        nxt_app_latency_record(status->latency, now,
                               now >= processing_start
                               ? now - processing_start : 0);
    }
}


void
nxt_app_status_response(nxt_app_status_t *status, nxt_uint_t code)
{
    if (code != NXT_HTTP_SWITCHING_PROTOCOLS
        && (code < NXT_HTTP_OK || code > NXT_HTTP_SERVER_ERROR_MAX))
    {
        return;
    }

    status->responses[code / 100 - 1]++;
}


nxt_buf_t *
nxt_app_status_report(nxt_task_t *task, nxt_mp_t *mp, nxt_queue_t *apps,
    nxt_queue_t *stopping_processes)
{
    u_char                    *p;
    size_t                    alloc;
    uint64_t                  buckets[NXT_APP_LATENCY_BUCKETS];
    uint64_t                  merged[NXT_APP_LATENCY_BUCKETS];
    nxt_app_t                 *app;
    nxt_buf_t                 *b;
    nxt_uint_t                i;
    nxt_app_status_info_t     *info;
    nxt_app_status_report_t   *report;
    nxt_router_app_process_t  *app_process;

    alloc = sizeof(nxt_app_status_report_t);

    nxt_queue_each(app, apps, nxt_app_t, link) {
        alloc += sizeof(nxt_app_status_info_t) + app->name.length;
    } nxt_queue_loop;

    b = nxt_buf_mem_alloc(mp, alloc, 0);
    if (nxt_slow_path(b == NULL)) {
        return NULL;
    }

    report = (nxt_app_status_report_t *) b->mem.free;
    b->mem.free = b->mem.end;

    nxt_memzero(report, sizeof(nxt_app_status_report_t));
    nxt_memzero(merged, sizeof(merged));

    info = report->apps;
    p = b->mem.end;

    nxt_queue_each(app, apps, nxt_app_t, link) {
        p -= app->name.length;
        nxt_memcpy(p, app->name.start, app->name.length);

        info->name.length = app->name.length;
        info->name.start = (u_char *) (p - b->mem.pos);

        nxt_thread_mutex_lock(&app->mutex);

        nxt_assert((uint64_t) app->waiting_requests + app->processing_requests
                   <= app->status.total_requests);

        info->total_requests = app->status.total_requests;
        nxt_memcpy(info->responses, app->status.responses,
                   sizeof(info->responses));
        info->waiting_requests = app->waiting_requests;
        info->processing_requests = app->processing_requests;
        nxt_memzero(buckets, sizeof(buckets));
        nxt_app_latency_merge(buckets, app->status.latency,
                              nxt_app_latency_now(task->thread));
        info->pending_processes = app->pending_processes;
        info->processes = app->processes;
        info->idle_processes = app->idle_processes;
        info->stopping_processes = 0;

        nxt_queue_each(app_process, stopping_processes,
                       nxt_router_app_process_t, stopping_link)
        {
            if (!nxt_strstr_eq(&app_process->name, &app->name)) {
                continue;
            }

            info->stopping_processes++;

            /* Restarted processes stay attached to finish their requests. */
            if (app_process->app == app) {
                info->processes--;

                if (app_process->idle_link.next != NULL) {
                    info->idle_processes--;
                }
            }
        } nxt_queue_loop;

        nxt_thread_mutex_unlock(&app->mutex);

        info->latency_valid = nxt_app_latency_percentiles(buckets,
                                                         info->latency);

        report->summary.total_requests += info->total_requests;
        report->summary.waiting_requests += info->waiting_requests;
        report->summary.processing_requests += info->processing_requests;
        report->summary.pending_processes += info->pending_processes;
        report->summary.processes += info->processes;
        report->summary.idle_processes += info->idle_processes;
        report->summary.stopping_processes += info->stopping_processes;

        for (i = 0; i < nxt_nitems(info->responses); i++) {
            report->summary.responses[i] += info->responses[i];
        }

        for (i = 0; i < NXT_APP_LATENCY_BUCKETS; i++) {
            merged[i] += buckets[i];
        }

        report->apps_count++;
        info++;
    } nxt_queue_loop;

    report->summary.latency_valid = nxt_app_latency_percentiles(merged,
                                                     report->summary.latency);

    return b;
}


static nxt_conf_value_t *nxt_app_status_metrics(nxt_app_status_info_t *app,
    nxt_mp_t *mp, nxt_uint_t members);


nxt_conf_value_t *
nxt_app_status_get(nxt_app_status_report_t *report, nxt_mp_t *mp)
{
    size_t                 i;
    nxt_str_t              name;
    nxt_int_t              ret;
    nxt_app_status_info_t  *app;
    nxt_conf_value_t       *status, *apps, *app_obj;

    static nxt_str_t apps_str = nxt_string("applications");

    status = nxt_app_status_metrics(&report->summary, mp, 5);
    if (nxt_slow_path(status == NULL)) {
        return NULL;
    }

    apps = nxt_conf_create_object(mp, report->apps_count);
    if (nxt_slow_path(apps == NULL)) {
        return NULL;
    }

    nxt_conf_set_member(status, &apps_str, apps, 4);

    for (i = 0; i < report->apps_count; i++) {
        app = &report->apps[i];

        app_obj = nxt_app_status_metrics(app, mp, 4);
        if (nxt_slow_path(app_obj == NULL)) {
            return NULL;
        }

        name.length = app->name.length;
        name.start = nxt_pointer_to(report, (uintptr_t) app->name.start);

        ret = nxt_conf_set_member_dup(apps, mp, &name, app_obj, i);
        if (nxt_slow_path(ret != NXT_OK)) {
            return NULL;
        }
    }

    return status;
}


static nxt_conf_value_t *
nxt_app_status_metrics(nxt_app_status_info_t *app, nxt_mp_t *mp,
    nxt_uint_t members)
{
    size_t            i;
    nxt_conf_value_t  *status, *obj;

    static nxt_str_t waiting_str = nxt_string("waiting");
    static nxt_str_t processing_str = nxt_string("processing");
    static nxt_str_t completed_str = nxt_string("completed");
    static nxt_str_t idle_str = nxt_string("idle");
    static nxt_str_t reqs_str = nxt_string("requests");
    static nxt_str_t resps_str = nxt_string("responses");
    static nxt_str_t latency_str = nxt_string("latency");
    static nxt_str_t total_str = nxt_string("total");
    static nxt_str_t procs_str = nxt_string("processes");
    static nxt_str_t run_str = nxt_string("running");
    static nxt_str_t start_str = nxt_string("starting");
    static nxt_str_t stop_str = nxt_string("stopping");

    static nxt_str_t response_classes[] = {
        nxt_string("1xx"),
        nxt_string("2xx"),
        nxt_string("3xx"),
        nxt_string("4xx"),
        nxt_string("5xx"),
    };

    static nxt_str_t percentiles[] = {
        nxt_string("p50"),
        nxt_string("p95"),
        nxt_string("p99"),
    };

    status = nxt_conf_create_object(mp, members);
    if (nxt_slow_path(status == NULL)) {
        return NULL;
    }

    obj = nxt_conf_create_object(mp, 4);
    if (nxt_slow_path(obj == NULL)) {
        return NULL;
    }

    nxt_conf_set_member(status, &procs_str, obj, 0);

    nxt_conf_set_member_integer(obj, &run_str, app->processes, 0);
    nxt_conf_set_member_integer(obj, &start_str, app->pending_processes, 1);
    nxt_conf_set_member_integer(obj, &idle_str, app->idle_processes, 2);
    nxt_conf_set_member_integer(obj, &stop_str, app->stopping_processes, 3);

    obj = nxt_conf_create_object(mp, 4);
    if (nxt_slow_path(obj == NULL)) {
        return NULL;
    }

    nxt_conf_set_member(status, &reqs_str, obj, 1);

    nxt_conf_set_member_integer(obj, &total_str, app->total_requests, 0);
    nxt_conf_set_member_integer(obj, &waiting_str, app->waiting_requests, 1);
    nxt_conf_set_member_integer(obj, &processing_str,
                               app->processing_requests, 2);
    nxt_conf_set_member_integer(obj, &completed_str,
                               app->total_requests - app->waiting_requests
                               - app->processing_requests, 3);

    obj = nxt_conf_create_object(mp, nxt_nitems(response_classes));
    if (nxt_slow_path(obj == NULL)) {
        return NULL;
    }

    nxt_conf_set_member(status, &resps_str, obj, 2);

    for (i = 0; i < nxt_nitems(response_classes); i++) {
        nxt_conf_set_member_integer(obj, &response_classes[i],
                                   app->responses[i], i);
    }

    obj = nxt_conf_create_object(mp, nxt_nitems(percentiles));
    if (nxt_slow_path(obj == NULL)) {
        return NULL;
    }

    nxt_conf_set_member(status, &latency_str, obj, 3);

    for (i = 0; i < nxt_nitems(percentiles); i++) {
        if (app->latency_valid) {
            nxt_conf_set_member_integer(obj, &percentiles[i],
                                       app->latency[i], i);

        } else {
            nxt_conf_set_member_null(obj, &percentiles[i], i);
        }
    }

    return status;
}
