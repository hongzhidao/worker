
/*
 * Copyright (C) NGINX, Inc.
 */

#include "worker.h"


napi_value
Init(napi_env env, napi_value exports)
{
    return Worker::init(env, exports);
}

NAPI_MODULE(Worker, Init)
