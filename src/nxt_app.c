#include <nxt_main.h>
#include <nxt_app.h>


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
nxt_app_latency_get(nxt_app_latency_t *latency, nxt_nsec_t now,
    uint64_t values[3])
{
    uint64_t                 second, count, cumulative, ranks[3];
    uint64_t                 buckets[NXT_APP_LATENCY_BUCKETS];
    nxt_uint_t               i, j, quantile, shift;
    nxt_app_latency_slice_t  *slice;

    static const uint8_t  percentages[] = { 50, 95, 99 };

    nxt_memzero(values, 3 * sizeof(uint64_t));

    if (latency == NULL) {
        return 0;
    }

    second = now / 1000000000;
    nxt_memzero(buckets, sizeof(buckets));

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
