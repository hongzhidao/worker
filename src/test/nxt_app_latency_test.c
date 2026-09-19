#include <nxt_main.h>
#include <nxt_app_status.h>
#include "nxt_tests.h"


#if (NXT_HAVE_CLOCK_MONOTONIC)

static nxt_nsec_t
nxt_app_latency_reference_time(void)
{
    struct timespec  ts;

    (void) clock_gettime(CLOCK_MONOTONIC, &ts);

    return (nxt_nsec_t) ts.tv_sec * 1000000000 + ts.tv_nsec;
}


static nxt_int_t
nxt_app_latency_clock_test(nxt_thread_t *thr, nxt_app_latency_t *latency)
{
    uint64_t    values[3];
    nxt_uint_t  attempts, samples;
    nxt_nsec_t  start_min, start_max, end_min, end_max, start, end;

    nxt_memzero(latency, sizeof(*latency));
    samples = 0;

    for (attempts = 0; attempts < 500 && samples < 100; attempts++) {
        start_min = nxt_app_latency_reference_time();
        start = nxt_app_latency_now(thr);
        start_max = nxt_app_latency_reference_time();

        do {
            end_min = nxt_app_latency_reference_time();
        } while (end_min - start_max < 2600000);

        end = nxt_app_latency_now(thr);
        end_max = nxt_app_latency_reference_time();

        /* Keep only intervals unambiguously rounding down to 2 ms. */
        if (end_min - start_max < 2500000
            || end_max - start_min >= 3000000)
        {
            continue;
        }

        if (end < start || (end - start) / 1000000 != 2) {
            nxt_log_error(NXT_LOG_ALERT, thr->log,
                          "app latency clock: expected 2 ms, got %uL ms",
                          (end - start) / 1000000);
            return NXT_ERROR;
        }

        nxt_app_latency_record(latency, end, end - start);
        samples++;
    }

    if (samples < 20
        || !nxt_app_latency_get(latency, nxt_app_latency_now(thr), values)
        || values[0] != 2 || values[1] != 2 || values[2] != 2)
    {
        return NXT_ERROR;
    }

    nxt_log_error(NXT_LOG_NOTICE, thr->log,
                  "app latency clock test passed: %ui samples", samples);
    return NXT_OK;
}

#endif


nxt_int_t
nxt_app_latency_test(nxt_thread_t *thr)
{
    uint64_t           values[3], msec;
    uint64_t           merged[NXT_APP_LATENCY_BUCKETS];
    nxt_uint_t         i;
    nxt_nsec_t         now;
    nxt_app_latency_t  *latency;

    latency = nxt_zalloc(sizeof(nxt_app_latency_t));
    if (latency == NULL) {
        return NXT_ERROR;
    }

    if (nxt_app_latency_get(NULL, 0, values)
        || nxt_app_latency_get(latency, 0, values))
    {
        goto fail;
    }

    nxt_app_latency_record(latency, 0, 0);
    if (!nxt_app_latency_get(latency, 0, values)
        || values[0] != 0 || values[1] != 0 || values[2] != 0)
    {
        goto fail;
    }

    nxt_memzero(latency, sizeof(*latency));

    for (i = 1; i <= 100; i++) {
        nxt_app_latency_record(latency, 0, (nxt_nsec_t) i * 1000000);
    }

    if (!nxt_app_latency_get(latency, 0, values)
        || values[0] != 51 || values[1] != 95 || values[2] != 99)
    {
        goto fail;
    }

    nxt_memzero(latency, sizeof(*latency));

    for (i = 0; i < 95; i++) {
        nxt_app_latency_record(latency, 0, 10 * 1000000);
    }

    for (i = 0; i < 4; i++) {
        nxt_app_latency_record(latency, 0, 100 * 1000000);
    }

    nxt_app_latency_record(latency, 0, 1000 * 1000000);

    if (!nxt_app_latency_get(latency, 0, values)
        || values[0] != 10 || values[1] != 10 || values[2] != 103)
    {
        goto fail;
    }

    nxt_memzero(latency, sizeof(*latency));
    nxt_app_latency_record(latency, 10ULL * 1000000000, 1000 * 1000000);
    nxt_app_latency_record(latency, 69ULL * 1000000000, 10 * 1000000);

    if (!nxt_app_latency_get(latency, 69ULL * 1000000000, values)
        || values[0] != 10 || values[1] != 1023 || values[2] != 1023)
    {
        goto fail;
    }

    if (!nxt_app_latency_get(latency, 70ULL * 1000000000, values)
        || values[0] != 10 || values[1] != 10 || values[2] != 10)
    {
        goto fail;
    }

    nxt_app_latency_record(latency, 70ULL * 1000000000, 20 * 1000000);
    nxt_app_latency_record(latency, 10ULL * 1000000000, 2000ULL * 1000000);

    if (!nxt_app_latency_get(latency, 70ULL * 1000000000, values)
        || values[0] != 10 || values[1] != 20 || values[2] != 20)
    {
        goto fail;
    }

    if (nxt_app_latency_get(latency, 130ULL * 1000000000, values)) {
        goto fail;
    }

    nxt_memzero(latency, sizeof(*latency));
    now = (nxt_nsec_t) NXT_INFINITE_MSEC * 1000000;
    nxt_app_latency_record(latency, now, NXT_INFINITE_NSEC);
    msec = NXT_INFINITE_NSEC / 1000000;

    if (!nxt_app_latency_get(latency, now + 59ULL * 1000000000, values)
        || values[0] < msec || values[0] > msec + msec / 16 + 1
        || values[0] != values[1] || values[1] != values[2])
    {
        goto fail;
    }

    if (nxt_app_latency_get(latency, now + 60ULL * 1000000000, values)) {
        goto fail;
    }

    nxt_memzero(latency, sizeof(*latency));
    latency->slices[0].buckets[1] = UINT64_MAX;

    if (!nxt_app_latency_get(latency, 0, values)
        || values[0] != 1 || values[1] != 1 || values[2] != 1)
    {
        goto fail;
    }

    nxt_memzero(latency, sizeof(*latency));
    nxt_memzero(merged, sizeof(merged));

    for (i = 0; i < 95; i++) {
        nxt_app_latency_record(latency, 0, 10 * 1000000);
    }

    nxt_app_latency_merge(merged, latency, 0);
    nxt_memzero(latency, sizeof(*latency));

    for (i = 0; i < 5; i++) {
        nxt_app_latency_record(latency, 0, 1000 * 1000000);
    }

    nxt_app_latency_merge(merged, latency, 0);

    if (!nxt_app_latency_percentiles(merged, values)
        || values[0] != 10 || values[1] != 10 || values[2] != 1023)
    {
        goto fail;
    }

    if (!nxt_app_latency_get(latency, 0, values)
        || values[0] != 1023 || values[1] != 1023 || values[2] != 1023)
    {
        goto fail;
    }

    nxt_memzero(merged, sizeof(merged));
    nxt_app_latency_merge(merged, NULL, 0);
    nxt_app_latency_merge(merged, latency, 60ULL * 1000000000);

    if (nxt_app_latency_percentiles(merged, values)) {
        goto fail;
    }

#if (NXT_HAVE_CLOCK_MONOTONIC)
    if (nxt_app_latency_clock_test(thr, latency) != NXT_OK) {
        goto fail;
    }
#endif

    nxt_free(latency);
    nxt_log_error(NXT_LOG_NOTICE, thr->log, "app latency test passed");
    return NXT_OK;

fail:

    nxt_free(latency);
    nxt_log_error(NXT_LOG_ALERT, thr->log, "app latency test failed");
    return NXT_ERROR;
}
