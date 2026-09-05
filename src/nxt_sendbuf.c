
/*
 * Copyright (C) Igor Sysoev
 * Copyright (C) NGINX, Inc.
 */

#include <nxt_main.h>


static nxt_buf_t *nxt_sendbuf_coalesce_completion(nxt_task_t *task,
    nxt_work_queue_t *wq, nxt_buf_t *start);


nxt_uint_t
nxt_sendbuf_mem_coalesce0(nxt_task_t *task, nxt_sendbuf_t *sb,
    struct iovec *iov, nxt_uint_t niov_max)
{
    u_char      *last;
    size_t      size, total;
    nxt_buf_t   *b;
    nxt_uint_t  n;

    total = sb->size;
    last = NULL;
    n = (nxt_uint_t) -1;

    for (b = sb->buf; b != NULL && total < sb->limit; b = b->next) {

        nxt_prefetch(b->next);

        if (nxt_buf_is_file(b)) {
            break;
        }

        if (nxt_buf_is_mem(b)) {

            size = b->mem.free - b->mem.pos;

            if (size != 0) {

                if (total + size > sb->limit) {
                    size = sb->limit - total;

                    if (size == 0) {
                        break;
                    }
                }

                if (b->mem.pos != last) {

                    if (++n >= niov_max) {
                        goto done;
                    }

                    iov[n].iov_base = b->mem.pos;
                    iov[n].iov_len = size;

                } else {
                    iov[n].iov_len += size;
                }

                nxt_debug(task, "sendbuf: %ui, %p, %uz",
                          n, iov[n].iov_base, iov[n].iov_len);

                total += size;
                last = b->mem.pos + size;
            }

        } else {
            sb->sync = 1;
            sb->last |= nxt_buf_is_last(b);
        }
    }

    n++;

done:

    sb->buf = b;

    return n;
}


nxt_uint_t
nxt_sendbuf_mem_coalesce(nxt_task_t *task, nxt_sendbuf_coalesce_t *sb)
{
    u_char      *last;
    size_t      size, total;
    nxt_buf_t   *b;
    nxt_uint_t  n;

    total = sb->size;
    last = NULL;
    n = (nxt_uint_t) -1;

    for (b = sb->buf; b != NULL && total < sb->limit; b = b->next) {

        nxt_prefetch(b->next);

        if (nxt_buf_is_file(b)) {
            break;
        }

        if (nxt_buf_is_mem(b)) {

            size = b->mem.free - b->mem.pos;

            if (size != 0) {

                if (total + size > sb->limit) {
                    size = sb->limit - total;

                    sb->limit_reached = 1;

                    if (nxt_slow_path(size == 0)) {
                        break;
                    }
                }

                if (b->mem.pos != last) {

                    if (++n >= sb->nmax) {
                        sb->nmax_reached = 1;

                        goto done;
                    }

                    sb->iobuf[n].iov_base = b->mem.pos;
                    sb->iobuf[n].iov_len = size;

                } else {
                    sb->iobuf[n].iov_len += size;
                }

                nxt_debug(task, "sendbuf: %ui, %p, %uz",
                          n, sb->iobuf[n].iov_base, sb->iobuf[n].iov_len);

                total += size;
                last = b->mem.pos + size;
            }

        } else {
            sb->sync = 1;
            sb->last |= nxt_buf_is_last(b);
        }
    }

    n++;

done:

    sb->buf = b;
    sb->size = total;
    sb->niov = n;

    return n;
}


size_t
nxt_sendbuf_file_coalesce(nxt_sendbuf_coalesce_t *sb)
{
    size_t     file_start, total;
    nxt_fd_t   fd;
    nxt_off_t  size, last;
    nxt_buf_t  *b;

    b = sb->buf;
    fd = b->file->fd;

    total = sb->size;

    for ( ;; ) {

        nxt_prefetch(b->next);

        size = b->file_end - b->file_pos;

        if (total + size >= sb->limit) {
            total = sb->limit;
            break;
        }

        total += size;
        last = b->file_pos + size;

        b = b->next;

        if (b == NULL || !nxt_buf_is_file(b)) {
            break;
        }

        if (b->file_pos != last || b->file->fd != fd) {
            break;
        }
    }

    sb->buf = b;

    file_start = sb->size;
    sb->size = total;

    return total - file_start;
}


nxt_buf_t *
nxt_sendbuf_update(nxt_buf_t *b, size_t sent)
{
    size_t  size;

    while (b != NULL) {

        nxt_prefetch(b->next);

        if (!nxt_buf_is_sync(b)) {

            size = nxt_buf_used_size(b);

            if (size != 0) {

                if (sent == 0) {
                    break;
                }

                if (sent < size) {

                    if (nxt_buf_is_mem(b)) {
                        b->mem.pos += sent;
                    }

                    if (nxt_buf_is_file(b)) {
                        b->file_pos += sent;
                    }

                    break;
                }

                /* b->mem.free is NULL in file-only buffer. */
                b->mem.pos = b->mem.free;

                if (nxt_buf_is_file(b)) {
                    b->file_pos = b->file_end;
                }

                sent -= size;
            }
        }

        b = b->next;
    }

    return b;
}


nxt_buf_t *
nxt_sendbuf_completion(nxt_task_t *task, nxt_work_queue_t *wq, nxt_buf_t *b)
{
    while (b != NULL) {

        if (!nxt_buf_is_sync(b) && nxt_buf_used_size(b) != 0) {
            break;
        }

        b = nxt_sendbuf_coalesce_completion(task, wq, b);
    }

    return b;
}


void
nxt_sendbuf_drain(nxt_task_t *task, nxt_work_queue_t *wq, nxt_buf_t *b)
{
    while (b != NULL) {
        b = nxt_sendbuf_coalesce_completion(task, wq, b);
    }
}


static nxt_buf_t *
nxt_sendbuf_coalesce_completion(nxt_task_t *task, nxt_work_queue_t *wq,
    nxt_buf_t *start)
{
    nxt_buf_t           *b, *next, **last, *rest, **last_rest;
    nxt_work_handler_t  handler;

    rest = NULL;
    last_rest = &rest;
    last = &start->next;
    b = start;
    handler = b->completion_handler;

    for ( ;; ) {
        next = b->next;
        if (next == NULL) {
            break;
        }

        b->next = NULL;
        b = next;

        if (!nxt_buf_is_sync(b) && nxt_buf_used_size(b) != 0) {
            *last_rest = b;
            break;
        }

        if (handler == b->completion_handler) {
            *last = b;
            last = &b->next;

        } else {
            *last_rest = b;
            last_rest = &b->next;
        }
    }

    nxt_work_queue_add(wq, handler, task, start, start->parent);

    return rest;
}
