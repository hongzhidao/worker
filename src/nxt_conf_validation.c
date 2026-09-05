
/*
 * Copyright (C) Valentin V. Bartenev
 * Copyright (C) NGINX, Inc.
 */

#include <nxt_main.h>
#include <nxt_conf.h>
#include <nxt_script.h>
#include <nxt_router.h>
#include <nxt_http.h>
#include <nxt_sockaddr.h>


typedef enum {
    NXT_CONF_VLDT_NULL    = 1 << NXT_CONF_NULL,
    NXT_CONF_VLDT_BOOLEAN = 1 << NXT_CONF_BOOLEAN,
    NXT_CONF_VLDT_INTEGER = 1 << NXT_CONF_INTEGER,
    NXT_CONF_VLDT_NUMBER  = (1 << NXT_CONF_NUMBER) | NXT_CONF_VLDT_INTEGER,
    NXT_CONF_VLDT_STRING  = 1 << NXT_CONF_STRING,
    NXT_CONF_VLDT_ARRAY   = 1 << NXT_CONF_ARRAY,
    NXT_CONF_VLDT_OBJECT  = 1 << NXT_CONF_OBJECT,
} nxt_conf_vldt_type_t;

#define NXT_CONF_VLDT_ANY_TYPE  (NXT_CONF_VLDT_NULL                           \
                                 |NXT_CONF_VLDT_BOOLEAN                       \
                                 |NXT_CONF_VLDT_NUMBER                        \
                                 |NXT_CONF_VLDT_STRING                        \
                                 |NXT_CONF_VLDT_ARRAY                         \
                                 |NXT_CONF_VLDT_OBJECT)


typedef enum {
    NXT_CONF_VLDT_REQUIRED  = 1 << 0,
    NXT_CONF_VLDT_TSTR      = 1 << 1,
} nxt_conf_vldt_flags_t;


typedef nxt_int_t (*nxt_conf_vldt_handler_t)(nxt_conf_validation_t *vldt,
                                             nxt_conf_value_t *value,
                                             void *data);
typedef nxt_int_t (*nxt_conf_vldt_member_t)(nxt_conf_validation_t *vldt,
                                            nxt_str_t *name,
                                            nxt_conf_value_t *value);
typedef nxt_int_t (*nxt_conf_vldt_element_t)(nxt_conf_validation_t *vldt,
                                             nxt_conf_value_t *value);


typedef struct nxt_conf_vldt_object_s  nxt_conf_vldt_object_t;

struct nxt_conf_vldt_object_s {
    nxt_str_t                     name;
    nxt_conf_vldt_type_t          type:32;
    nxt_conf_vldt_flags_t         flags:32;
    nxt_conf_vldt_handler_t       validator;

    union {
        nxt_conf_vldt_object_t    *members;
        nxt_conf_vldt_object_t    *next;
        nxt_conf_vldt_member_t    object;
        nxt_conf_vldt_element_t   array;
        const char                *string;
    } u;
};


#define NXT_CONF_VLDT_NEXT(next)  { .u.members = next }
#define NXT_CONF_VLDT_END         { .name = nxt_null_string }


static nxt_int_t nxt_conf_vldt_type(nxt_conf_validation_t *vldt,
    nxt_str_t *name, nxt_conf_value_t *value, nxt_conf_vldt_type_t type);
static nxt_int_t nxt_conf_vldt_error(nxt_conf_validation_t *vldt,
    const char *fmt, ...);
static nxt_int_t nxt_conf_vldt_var(nxt_conf_validation_t *vldt, nxt_str_t *name,
    nxt_str_t *value);
nxt_inline nxt_int_t nxt_conf_vldt_unsupported(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);

static nxt_int_t nxt_conf_vldt_listener(nxt_conf_validation_t *vldt,
    nxt_str_t *name, nxt_conf_value_t *value);
static nxt_int_t nxt_conf_vldt_pass(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_python(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_python_path(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_python_path_element(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value);
static nxt_int_t nxt_conf_vldt_python_protocol(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_threads(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_thread_stack_size(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_app_name(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_app(nxt_conf_validation_t *vldt,
    nxt_str_t *name, nxt_conf_value_t *value);
static nxt_int_t nxt_conf_vldt_object(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_processes(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_object_iterator(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_array_iterator(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_environment(nxt_conf_validation_t *vldt,
    nxt_str_t *name, nxt_conf_value_t *value);
static nxt_int_t nxt_conf_vldt_targets_exclusive(
    nxt_conf_validation_t *vldt, nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_targets(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_target(nxt_conf_validation_t *vldt,
    nxt_str_t *name, nxt_conf_value_t *value);
static nxt_int_t nxt_conf_vldt_argument(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value);
static nxt_int_t nxt_conf_vldt_php(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_php_option(nxt_conf_validation_t *vldt,
    nxt_str_t *name, nxt_conf_value_t *value);

static nxt_int_t nxt_conf_vldt_isolation(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_clone_namespaces(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data);

#if (NXT_HAVE_CLONE_NEWUSER)
static nxt_int_t nxt_conf_vldt_clone_procmap(nxt_conf_validation_t *vldt,
    const char* mapfile, nxt_conf_value_t *value);
static nxt_int_t nxt_conf_vldt_clone_uidmap(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value);
static nxt_int_t nxt_conf_vldt_clone_gidmap(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value);
#endif

#if (NXT_HAVE_NJS)
static nxt_int_t nxt_conf_vldt_js_module(nxt_conf_validation_t *vldt,
     nxt_conf_value_t *value, void *data);
static nxt_int_t nxt_conf_vldt_js_module_element(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value);
#endif

static nxt_conf_vldt_object_t  nxt_conf_vldt_setting_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_http_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_websocket_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_python_target_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_php_common_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_php_options_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_php_target_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_common_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_app_limits_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_app_processes_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_app_isolation_members[];
static nxt_conf_vldt_object_t  nxt_conf_vldt_app_namespaces_members[];
#if (NXT_HAVE_ISOLATION_ROOTFS)
static nxt_conf_vldt_object_t  nxt_conf_vldt_app_automount_members[];
#endif


static nxt_conf_vldt_object_t  nxt_conf_vldt_root_members[] = {
    {
        .name       = nxt_string("settings"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object,
        .u.members  = nxt_conf_vldt_setting_members,
    }, {
        .name       = nxt_string("listeners"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object_iterator,
        .u.object   = nxt_conf_vldt_listener,
    }, {
        .name       = nxt_string("applications"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object_iterator,
        .u.object   = nxt_conf_vldt_app,
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_setting_members[] = {
    {
        .name       = nxt_string("http"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object,
        .u.members  = nxt_conf_vldt_http_members,
#if (NXT_HAVE_NJS)
    }, {
        .name       = nxt_string("js_module"),
        .type       = NXT_CONF_VLDT_STRING | NXT_CONF_VLDT_ARRAY,
        .validator  = nxt_conf_vldt_js_module,
#endif
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_http_members[] = {
    {
        .name       = nxt_string("header_read_timeout"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("body_read_timeout"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("send_timeout"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("idle_timeout"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("body_buffer_size"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("max_body_size"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("body_temp_path"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("discard_unsafe_fields"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    }, {
        .name       = nxt_string("websocket"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object,
        .u.members  = nxt_conf_vldt_websocket_members,
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_websocket_members[] = {
    {
        .name       = nxt_string("read_timeout"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {

        .name       = nxt_string("keepalive_interval"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("max_frame_size"),
        .type       = NXT_CONF_VLDT_INTEGER,
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_listener_members[] = {
    {
        .name       = nxt_string("pass"),
        .type       = NXT_CONF_VLDT_STRING,
        .validator  = nxt_conf_vldt_pass,
        .flags      = NXT_CONF_VLDT_TSTR,
    }, {
        .name       = nxt_string("application"),
        .type       = NXT_CONF_VLDT_STRING,
        .validator  = nxt_conf_vldt_app_name,
    },


    NXT_CONF_VLDT_END
};





static nxt_conf_vldt_object_t  nxt_conf_vldt_external_members[] = {
    {
        .name       = nxt_string("executable"),
        .type       = NXT_CONF_VLDT_STRING,
        .flags      = NXT_CONF_VLDT_REQUIRED,
    }, {
        .name       = nxt_string("arguments"),
        .type       = NXT_CONF_VLDT_ARRAY,
        .validator  = nxt_conf_vldt_array_iterator,
        .u.array    = nxt_conf_vldt_argument,
    },

    NXT_CONF_VLDT_NEXT(nxt_conf_vldt_common_members)
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_python_common_members[] = {
    {
        .name       = nxt_string("home"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("path"),
        .type       = NXT_CONF_VLDT_STRING | NXT_CONF_VLDT_ARRAY,
        .validator  = nxt_conf_vldt_python_path,
    }, {
        .name       = nxt_string("protocol"),
        .type       = NXT_CONF_VLDT_STRING,
        .validator  = nxt_conf_vldt_python_protocol,
    }, {
        .name       = nxt_string("threads"),
        .type       = NXT_CONF_VLDT_INTEGER,
        .validator  = nxt_conf_vldt_threads,
    }, {
        .name       = nxt_string("thread_stack_size"),
        .type       = NXT_CONF_VLDT_INTEGER,
        .validator  = nxt_conf_vldt_thread_stack_size,
    },

    NXT_CONF_VLDT_NEXT(nxt_conf_vldt_common_members)
};

static nxt_conf_vldt_object_t  nxt_conf_vldt_python_members[] = {
    {
        .name       = nxt_string("module"),
        .type       = NXT_CONF_VLDT_STRING,
        .validator  = nxt_conf_vldt_targets_exclusive,
        .u.string   = "module",
    }, {
        .name       = nxt_string("callable"),
        .type       = NXT_CONF_VLDT_STRING,
        .validator  = nxt_conf_vldt_targets_exclusive,
        .u.string   = "callable",
    }, {
        .name       = nxt_string("factory"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
        .validator  = nxt_conf_vldt_targets_exclusive,
        .u.string   = "factory",
    }, {
        .name       = nxt_string("targets"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_targets,
        .u.members  = nxt_conf_vldt_python_target_members
    },

    NXT_CONF_VLDT_NEXT(nxt_conf_vldt_python_common_members)
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_python_target_members[] = {
    {
        .name       = nxt_string("module"),
        .type       = NXT_CONF_VLDT_STRING,
        .flags      = NXT_CONF_VLDT_REQUIRED,
    }, {
        .name       = nxt_string("callable"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("factory"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_python_notargets_members[] = {
    {
        .name       = nxt_string("module"),
        .type       = NXT_CONF_VLDT_STRING,
        .flags      = NXT_CONF_VLDT_REQUIRED,
    }, {
        .name       = nxt_string("callable"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("factory"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },

    NXT_CONF_VLDT_NEXT(nxt_conf_vldt_python_common_members)
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_php_members[] = {
    {
        .name       = nxt_string("root"),
        .type       = NXT_CONF_VLDT_ANY_TYPE,
        .validator  = nxt_conf_vldt_targets_exclusive,
        .u.string   = "root",
    }, {
        .name       = nxt_string("script"),
        .type       = NXT_CONF_VLDT_ANY_TYPE,
        .validator  = nxt_conf_vldt_targets_exclusive,
        .u.string   = "script",
    }, {
        .name       = nxt_string("index"),
        .type       = NXT_CONF_VLDT_ANY_TYPE,
        .validator  = nxt_conf_vldt_targets_exclusive,
        .u.string   = "index",
    }, {
        .name       = nxt_string("targets"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_targets,
        .u.members  = nxt_conf_vldt_php_target_members
    },

    NXT_CONF_VLDT_NEXT(nxt_conf_vldt_php_common_members)
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_php_common_members[] = {
    {
        .name       = nxt_string("options"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object,
        .u.members  = nxt_conf_vldt_php_options_members,
    },

    NXT_CONF_VLDT_NEXT(nxt_conf_vldt_common_members)
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_php_options_members[] = {
    {
        .name       = nxt_string("file"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("admin"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object_iterator,
        .u.object   = nxt_conf_vldt_php_option,
    }, {
        .name       = nxt_string("user"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object_iterator,
        .u.object   = nxt_conf_vldt_php_option,
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_php_target_members[] = {
    {
        .name       = nxt_string("root"),
        .type       = NXT_CONF_VLDT_STRING,
        .flags      = NXT_CONF_VLDT_REQUIRED,
    }, {
        .name       = nxt_string("script"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("index"),
        .type       = NXT_CONF_VLDT_STRING,
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_php_notargets_members[] = {
    {
        .name       = nxt_string("root"),
        .type       = NXT_CONF_VLDT_STRING,
        .flags      = NXT_CONF_VLDT_REQUIRED,
    }, {
        .name       = nxt_string("script"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("index"),
        .type       = NXT_CONF_VLDT_STRING,
    },

    NXT_CONF_VLDT_NEXT(nxt_conf_vldt_php_common_members)
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_ruby_members[] = {
    {
        .name       = nxt_string("script"),
        .type       = NXT_CONF_VLDT_STRING,
        .flags      = NXT_CONF_VLDT_REQUIRED,
    }, {
        .name       = nxt_string("threads"),
        .type       = NXT_CONF_VLDT_INTEGER,
        .validator  = nxt_conf_vldt_threads,
    }, {
        .name       = nxt_string("hooks"),
        .type       = NXT_CONF_VLDT_STRING
    },

    NXT_CONF_VLDT_NEXT(nxt_conf_vldt_common_members)
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_common_members[] = {
    {
        .name       = nxt_string("type"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("limits"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object,
        .u.members  = nxt_conf_vldt_app_limits_members,
    }, {
        .name       = nxt_string("processes"),
        .type       = NXT_CONF_VLDT_INTEGER | NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_processes,
        .u.members  = nxt_conf_vldt_app_processes_members,
    }, {
        .name       = nxt_string("user"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("group"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("working_directory"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("environment"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object_iterator,
        .u.object   = nxt_conf_vldt_environment,
    }, {
        .name       = nxt_string("isolation"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_isolation,
        .u.members  = nxt_conf_vldt_app_isolation_members,
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_app_limits_members[] = {
    {
        .name       = nxt_string("timeout"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("requests"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("shm"),
        .type       = NXT_CONF_VLDT_INTEGER,
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_app_processes_members[] = {
    {
        .name       = nxt_string("spare"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("max"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("idle_timeout"),
        .type       = NXT_CONF_VLDT_INTEGER,
    },

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_app_isolation_members[] = {
    {
        .name       = nxt_string("namespaces"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_clone_namespaces,
        .u.members  = nxt_conf_vldt_app_namespaces_members,
    },

#if (NXT_HAVE_CLONE_NEWUSER)
    {
        .name       = nxt_string("uidmap"),
        .type       = NXT_CONF_VLDT_ARRAY,
        .validator  = nxt_conf_vldt_array_iterator,
        .u.array    = nxt_conf_vldt_clone_uidmap,
    }, {
        .name       = nxt_string("gidmap"),
        .type       = NXT_CONF_VLDT_ARRAY,
        .validator  = nxt_conf_vldt_array_iterator,
        .u.array    = nxt_conf_vldt_clone_gidmap,
    },
#endif

#if (NXT_HAVE_ISOLATION_ROOTFS)
    {
        .name       = nxt_string("rootfs"),
        .type       = NXT_CONF_VLDT_STRING,
    }, {
        .name       = nxt_string("automount"),
        .type       = NXT_CONF_VLDT_OBJECT,
        .validator  = nxt_conf_vldt_object,
        .u.members  = nxt_conf_vldt_app_automount_members,
    },
#endif

#if (NXT_HAVE_PR_SET_NO_NEW_PRIVS)
    {
        .name       = nxt_string("new_privs"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },
#endif

    NXT_CONF_VLDT_END
};


static nxt_conf_vldt_object_t  nxt_conf_vldt_app_namespaces_members[] = {

#if (NXT_HAVE_CLONE_NEWUSER)
    {
        .name       = nxt_string("credential"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },
#endif

#if (NXT_HAVE_CLONE_NEWPID)
    {
        .name       = nxt_string("pid"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },
#endif

#if (NXT_HAVE_CLONE_NEWNET)
    {
        .name       = nxt_string("network"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },
#endif

#if (NXT_HAVE_CLONE_NEWNS)
    {
        .name       = nxt_string("mount"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },
#endif

#if (NXT_HAVE_CLONE_NEWUTS)
    {
        .name       = nxt_string("uname"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },
#endif

#if (NXT_HAVE_CLONE_NEWCGROUP)
    {
        .name       = nxt_string("cgroup"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },
#endif

    NXT_CONF_VLDT_END
};


#if (NXT_HAVE_ISOLATION_ROOTFS)

static nxt_conf_vldt_object_t  nxt_conf_vldt_app_automount_members[] = {
    {
        .name       = nxt_string("language_deps"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    }, {
        .name       = nxt_string("tmpfs"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    }, {
        .name       = nxt_string("procfs"),
        .type       = NXT_CONF_VLDT_BOOLEAN,
    },

    NXT_CONF_VLDT_END
};

#endif


#if (NXT_HAVE_CLONE_NEWUSER)

static nxt_conf_vldt_object_t nxt_conf_vldt_app_procmap_members[] = {
    {
        .name       = nxt_string("container"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("host"),
        .type       = NXT_CONF_VLDT_INTEGER,
    }, {
        .name       = nxt_string("size"),
        .type       = NXT_CONF_VLDT_INTEGER,
    },

    NXT_CONF_VLDT_END
};

#endif


nxt_int_t
nxt_conf_validate(nxt_conf_validation_t *vldt)
{
    nxt_int_t  ret;
    u_char     error[NXT_MAX_ERROR_STR];

    vldt->tstr_state = nxt_tstr_state_new(vldt->pool, 1);
    if (nxt_slow_path(vldt->tstr_state == NULL)) {
        return NXT_ERROR;
    }

    ret = nxt_conf_vldt_type(vldt, NULL, vldt->conf, NXT_CONF_VLDT_OBJECT);
    if (ret != NXT_OK) {
        return ret;
    }

    ret = nxt_conf_vldt_object(vldt, vldt->conf, nxt_conf_vldt_root_members);
    if (ret != NXT_OK) {
        return ret;
    }

    ret = nxt_tstr_state_done(vldt->tstr_state, error);
    if (ret != NXT_OK) {
        ret = nxt_conf_vldt_error(vldt, "%s", error);
        return ret;
    }

    return NXT_OK;
}


#define NXT_CONF_VLDT_ANY_TYPE_STR                                            \
    "either a null, a boolean, an integer, "                                  \
    "a number, a string, an array, or an object"


static nxt_int_t
nxt_conf_vldt_type(nxt_conf_validation_t *vldt, nxt_str_t *name,
    nxt_conf_value_t *value, nxt_conf_vldt_type_t type)
{
    u_char      *p;
    nxt_str_t   expected;
    nxt_bool_t  comma;
    nxt_uint_t  value_type, n, t;
    u_char      buf[nxt_length(NXT_CONF_VLDT_ANY_TYPE_STR)];

    static nxt_str_t  type_name[] = {
        nxt_string("a null"),
        nxt_string("a boolean"),
        nxt_string("an integer number"),
        nxt_string("a fractional number"),
        nxt_string("a string"),
        nxt_string("an array"),
        nxt_string("an object"),
    };

    value_type = nxt_conf_type(value);

    if ((1 << value_type) & type) {
        return NXT_OK;
    }

    p = buf;

    n = nxt_popcount(type);

    if (n > 1) {
        p = nxt_cpymem(p, "either ", 7);
    }

    comma = (n > 2);

    for ( ;; ) {
        t = __builtin_ffs(type) - 1;

        p = nxt_cpymem(p, type_name[t].start, type_name[t].length);

        n--;

        if (n == 0) {
            break;
        }

        if (comma) {
            *p++ = ',';
        }

        if (n == 1) {
            p = nxt_cpymem(p, " or", 3);
        }

        *p++ = ' ';

        type = type & ~(1 << t);
    }

    expected.length = p - buf;
    expected.start = buf;

    if (name == NULL) {
        return nxt_conf_vldt_error(vldt,
                                   "The configuration must be %V, but not %V.",
                                   &expected, &type_name[value_type]);
    }

    return nxt_conf_vldt_error(vldt,
                               "The \"%V\" value must be %V, but not %V.",
                               name, &expected, &type_name[value_type]);
}


static nxt_int_t
nxt_conf_vldt_error(nxt_conf_validation_t *vldt, const char *fmt, ...)
{
    u_char   *p, *end;
    size_t   size;
    va_list  args;
    u_char   error[NXT_MAX_ERROR_STR];

    va_start(args, fmt);
    end = nxt_vsprintf(error, error + NXT_MAX_ERROR_STR, fmt, args);
    va_end(args);

    size = end - error;

    p = nxt_mp_nget(vldt->pool, size);
    if (p == NULL) {
        return NXT_ERROR;
    }

    nxt_memcpy(p, error, size);

    vldt->error.length = size;
    vldt->error.start = p;

    return NXT_DECLINED;
}


nxt_inline nxt_int_t
nxt_conf_vldt_unsupported(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    return nxt_conf_vldt_error(vldt, "Worker is built without the \"%s\" "
                                     "option support.", data);
}


static nxt_int_t
nxt_conf_vldt_var(nxt_conf_validation_t *vldt, nxt_str_t *name,
    nxt_str_t *value)
{
    u_char  error[NXT_MAX_ERROR_STR];

    if (nxt_tstr_test(vldt->tstr_state, value, error) != NXT_OK) {
        return nxt_conf_vldt_error(vldt, "%s in the \"%V\" value.",
                                   error, name);
    }

    return NXT_OK;
}


static nxt_int_t
nxt_conf_vldt_listener(nxt_conf_validation_t *vldt, nxt_str_t *name,
    nxt_conf_value_t *value)
{
    nxt_int_t       ret;
    nxt_sockaddr_t  *sa;

    sa = nxt_sockaddr_parse(vldt->pool, name);
    if (nxt_slow_path(sa == NULL)) {
        return nxt_conf_vldt_error(vldt,
                                   "The listener address \"%V\" is invalid.",
                                   name);
    }

    ret = nxt_conf_vldt_type(vldt, name, value, NXT_CONF_VLDT_OBJECT);
    if (ret != NXT_OK) {
        return ret;
    }

    return nxt_conf_vldt_object(vldt, value, nxt_conf_vldt_listener_members);
}


static nxt_int_t
nxt_conf_vldt_pass(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    nxt_str_t  pass;
    nxt_int_t  ret;
    nxt_str_t  segments[3];

    static nxt_str_t  targets_str = nxt_string("targets");

    nxt_conf_get_string(value, &pass);

    ret = nxt_http_pass_segments(vldt->pool, &pass, segments, 3);

    if (ret != NXT_OK) {
        if (ret == NXT_DECLINED) {
            return nxt_conf_vldt_error(vldt, "Request \"pass\" value \"%V\" "
                                       "is invalid.", &pass);
        }

        return NXT_ERROR;
    }

    if (nxt_str_eq(&segments[0], "applications", 12)) {

        if (segments[1].length == 0) {
            goto error;
        }

        value = nxt_conf_get_object_member(vldt->conf, &segments[0], NULL);

        if (value == NULL) {
            goto error;
        }

        value = nxt_conf_get_object_member(value, &segments[1], NULL);

        if (value == NULL) {
            goto error;
        }

        if (segments[2].length > 0) {
            value = nxt_conf_get_object_member(value, &targets_str, NULL);

            if (value == NULL) {
                goto error;
            }

            value = nxt_conf_get_object_member(value, &segments[2], NULL);

            if (value == NULL) {
                goto error;
            }
        }

        return NXT_OK;
    }

error:

    return nxt_conf_vldt_error(vldt, "Request \"pass\" points to invalid "
                               "location \"%V\".", &pass);
}


static nxt_int_t
nxt_conf_vldt_python(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    nxt_conf_value_t  *targets;

    static nxt_str_t  targets_str = nxt_string("targets");

    targets = nxt_conf_get_object_member(value, &targets_str, NULL);

    if (targets != NULL) {
        return nxt_conf_vldt_object(vldt, value, nxt_conf_vldt_python_members);
    }

    return nxt_conf_vldt_object(vldt, value,
                                nxt_conf_vldt_python_notargets_members);
}


static nxt_int_t
nxt_conf_vldt_python_path(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data)
{
    if (nxt_conf_type(value) == NXT_CONF_ARRAY) {
        return nxt_conf_vldt_array_iterator(vldt, value,
                                            &nxt_conf_vldt_python_path_element);
    }

    /* NXT_CONF_STRING */

    return NXT_OK;
}


static nxt_int_t
nxt_conf_vldt_python_path_element(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value)
{
    if (nxt_conf_type(value) != NXT_CONF_STRING) {
        return nxt_conf_vldt_error(vldt, "The \"path\" array must contain "
                                   "only string values.");
    }

    return NXT_OK;
}


static nxt_int_t
nxt_conf_vldt_python_protocol(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data)
{
    nxt_str_t  proto;

    static const nxt_str_t  wsgi = nxt_string("wsgi");
    static const nxt_str_t  asgi = nxt_string("asgi");

    nxt_conf_get_string(value, &proto);

    if (nxt_strstr_eq(&proto, &wsgi) || nxt_strstr_eq(&proto, &asgi)) {
        return NXT_OK;
    }

    return nxt_conf_vldt_error(vldt, "The \"protocol\" can either be "
                                     "\"wsgi\" or \"asgi\".");
}


static nxt_int_t
nxt_conf_vldt_threads(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    int64_t  threads;

    threads = nxt_conf_get_number(value);

    if (threads < 1) {
        return nxt_conf_vldt_error(vldt, "The \"threads\" number must be "
                                   "equal to or greater than 1.");
    }

    if (threads > NXT_INT32_T_MAX) {
        return nxt_conf_vldt_error(vldt, "The \"threads\" number must "
                                   "not exceed %d.", NXT_INT32_T_MAX);
    }

    return NXT_OK;
}


static nxt_int_t
nxt_conf_vldt_thread_stack_size(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data)
{
    int64_t  size, min_size;

    size = nxt_conf_get_number(value);
    min_size = sysconf(_SC_THREAD_STACK_MIN);

    if (size < min_size) {
        return nxt_conf_vldt_error(vldt, "The \"thread_stack_size\" number "
                                   "must be equal to or greater than %d.",
                                   min_size);
    }

    if ((size % nxt_pagesize) != 0) {
        return nxt_conf_vldt_error(vldt, "The \"thread_stack_size\" number "
                             "must be a multiple of the system page size (%d).",
                             nxt_pagesize);
    }

    return NXT_OK;
}


static nxt_int_t
nxt_conf_vldt_app_name(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    nxt_str_t         name;
    nxt_conf_value_t  *apps, *app;

    static nxt_str_t  apps_str = nxt_string("applications");

    nxt_conf_get_string(value, &name);

    apps = nxt_conf_get_object_member(vldt->conf, &apps_str, NULL);

    if (nxt_slow_path(apps == NULL)) {
        goto error;
    }

    app = nxt_conf_get_object_member(apps, &name, NULL);

    if (nxt_slow_path(app == NULL)) {
        goto error;
    }

    return NXT_OK;

error:

    return nxt_conf_vldt_error(vldt, "Listening socket is assigned for "
                                     "a non existing application \"%V\".",
                                     &name);
}


static nxt_int_t
nxt_conf_vldt_app(nxt_conf_validation_t *vldt, nxt_str_t *name,
    nxt_conf_value_t *value)
{
    nxt_int_t              ret;
    nxt_str_t              type;
    nxt_thread_t           *thread;
    nxt_conf_value_t       *type_value;
    nxt_app_lang_module_t  *lang;

    static nxt_str_t  type_str = nxt_string("type");

    static struct {
        nxt_conf_vldt_handler_t  validator;
        nxt_conf_vldt_object_t   *members;

    } types[] = {
        { nxt_conf_vldt_object, nxt_conf_vldt_external_members },
        { nxt_conf_vldt_python, NULL },
        { nxt_conf_vldt_php,    NULL },
        { nxt_conf_vldt_object, nxt_conf_vldt_ruby_members },
    };

    ret = nxt_conf_vldt_type(vldt, name, value, NXT_CONF_VLDT_OBJECT);

    if (ret != NXT_OK) {
        return ret;
    }

    type_value = nxt_conf_get_object_member(value, &type_str, NULL);

    if (type_value == NULL) {
        return nxt_conf_vldt_error(vldt,
                           "Application must have the \"type\" property set.");
    }

    ret = nxt_conf_vldt_type(vldt, &type_str, type_value, NXT_CONF_VLDT_STRING);

    if (ret != NXT_OK) {
        return ret;
    }

    nxt_conf_get_string(type_value, &type);

    thread = nxt_thread();

    lang = nxt_app_lang_module(thread->runtime, &type);
    if (lang == NULL) {
        return nxt_conf_vldt_error(vldt,
                                   "The module to run \"%V\" is not found "
                                   "among the available application modules.",
                                   &type);
    }

    return types[lang->type].validator(vldt, value, types[lang->type].members);
}


static nxt_int_t
nxt_conf_vldt_object(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    uint32_t                index;
    nxt_int_t               ret;
    nxt_str_t               name, var;
    nxt_conf_value_t        *member;
    nxt_conf_vldt_object_t  *vals;

    vals = data;

    for ( ;; ) {
        if (vals->name.length == 0) {

            if (vals->u.members != NULL) {
                vals = vals->u.members;
                continue;
            }

            break;
        }

        if (vals->flags & NXT_CONF_VLDT_REQUIRED) {
            member = nxt_conf_get_object_member(value, &vals->name, NULL);

            if (member == NULL) {
                return nxt_conf_vldt_error(vldt, "Required parameter \"%V\" "
                                           "is missing.", &vals->name);
            }
        }

        vals++;
    }

    index = 0;

    for ( ;; ) {
        member = nxt_conf_next_object_member(value, &name, &index);

        if (member == NULL) {
            return NXT_OK;
        }

        vals = data;

        for ( ;; ) {
            if (vals->name.length == 0) {

                if (vals->u.members != NULL) {
                    vals = vals->u.members;
                    continue;
                }

                return nxt_conf_vldt_error(vldt, "Unknown parameter \"%V\".",
                                           &name);
            }

            if (!nxt_strstr_eq(&vals->name, &name)) {
                vals++;
                continue;
            }

            if (vals->flags & NXT_CONF_VLDT_TSTR
                && nxt_conf_type(member) == NXT_CONF_STRING)
            {
                nxt_conf_get_string(member, &var);

                if (nxt_is_tstr(&var)) {
                    ret = nxt_conf_vldt_var(vldt, &name, &var);
                    if (ret != NXT_OK) {
                        return ret;
                    }

                    break;
                }
           }

            ret = nxt_conf_vldt_type(vldt, &name, member, vals->type);
            if (ret != NXT_OK) {
                return ret;
            }

            if (vals->validator != NULL) {
                ret = vals->validator(vldt, member, vals->u.members);

                if (ret != NXT_OK) {
                    return ret;
                }
            }

            break;
        }
    }
}


typedef struct {
    int64_t  spare;
    int64_t  max;
    int64_t  idle_timeout;
} nxt_conf_vldt_processes_conf_t;


static nxt_conf_map_t  nxt_conf_vldt_processes_conf_map[] = {
    {
        nxt_string("spare"),
        NXT_CONF_MAP_INT64,
        offsetof(nxt_conf_vldt_processes_conf_t, spare),
    },

    {
        nxt_string("max"),
        NXT_CONF_MAP_INT64,
        offsetof(nxt_conf_vldt_processes_conf_t, max),
    },

    {
        nxt_string("idle_timeout"),
        NXT_CONF_MAP_INT64,
        offsetof(nxt_conf_vldt_processes_conf_t, idle_timeout),
    },
};


static nxt_int_t
nxt_conf_vldt_processes(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    int64_t                         int_value;
    nxt_int_t                       ret;
    nxt_conf_vldt_processes_conf_t  proc;

    if (nxt_conf_type(value) == NXT_CONF_INTEGER) {
        int_value = nxt_conf_get_number(value);

        if (int_value < 1) {
            return nxt_conf_vldt_error(vldt, "The \"processes\" number must be "
                                       "equal to or greater than 1.");
        }

        if (int_value > NXT_INT32_T_MAX) {
            return nxt_conf_vldt_error(vldt, "The \"processes\" number must "
                                       "not exceed %d.", NXT_INT32_T_MAX);
        }

        return NXT_OK;
    }

    ret = nxt_conf_vldt_object(vldt, value, data);
    if (ret != NXT_OK) {
        return ret;
    }

    proc.spare = 0;
    proc.max = 1;
    proc.idle_timeout = 15;

    ret = nxt_conf_map_object(vldt->pool, value,
                              nxt_conf_vldt_processes_conf_map,
                              nxt_nitems(nxt_conf_vldt_processes_conf_map),
                              &proc);
    if (ret != NXT_OK) {
        return ret;
    }

    if (proc.spare < 0) {
        return nxt_conf_vldt_error(vldt, "The \"spare\" number must not be "
                                   "negative.");
    }

    if (proc.spare > NXT_INT32_T_MAX) {
        return nxt_conf_vldt_error(vldt, "The \"spare\" number must not "
                                   "exceed %d.", NXT_INT32_T_MAX);
    }

    if (proc.max < 1) {
        return nxt_conf_vldt_error(vldt, "The \"max\" number must be equal "
                                   "to or greater than 1.");
    }

    if (proc.max > NXT_INT32_T_MAX) {
        return nxt_conf_vldt_error(vldt, "The \"max\" number must not "
                                   "exceed %d.", NXT_INT32_T_MAX);
    }

    if (proc.max < proc.spare) {
        return nxt_conf_vldt_error(vldt, "The \"spare\" number must be "
                                   "less than or equal to \"max\".");
    }

    if (proc.idle_timeout < 0) {
        return nxt_conf_vldt_error(vldt, "The \"idle_timeout\" number must not "
                                   "be negative.");
    }

    if (proc.idle_timeout > NXT_INT32_T_MAX / 1000) {
        return nxt_conf_vldt_error(vldt, "The \"idle_timeout\" number must not "
                                   "exceed %d.", NXT_INT32_T_MAX / 1000);
    }

    return NXT_OK;
}


static nxt_int_t
nxt_conf_vldt_object_iterator(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data)
{
    uint32_t                index;
    nxt_int_t               ret;
    nxt_str_t               name;
    nxt_conf_value_t        *member;
    nxt_conf_vldt_member_t  validator;

    validator = (nxt_conf_vldt_member_t) data;
    index = 0;

    for ( ;; ) {
        member = nxt_conf_next_object_member(value, &name, &index);

        if (member == NULL) {
            return NXT_OK;
        }

        ret = validator(vldt, &name, member);

        if (ret != NXT_OK) {
            return ret;
        }
    }
}


static nxt_int_t
nxt_conf_vldt_array_iterator(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data)
{
    uint32_t                 index;
    nxt_int_t                ret;
    nxt_conf_value_t         *element;
    nxt_conf_vldt_element_t  validator;

    validator = (nxt_conf_vldt_element_t) data;

    for (index = 0; /* void */ ; index++) {
        element = nxt_conf_get_array_element(value, index);

        if (element == NULL) {
            return NXT_OK;
        }

        ret = validator(vldt, element);

        if (ret != NXT_OK) {
            return ret;
        }
    }
}


static nxt_int_t
nxt_conf_vldt_environment(nxt_conf_validation_t *vldt, nxt_str_t *name,
    nxt_conf_value_t *value)
{
    nxt_str_t  str;

    if (name->length == 0) {
        return nxt_conf_vldt_error(vldt,
                                   "The environment name must not be empty.");
    }

    if (nxt_memchr(name->start, '\0', name->length) != NULL) {
        return nxt_conf_vldt_error(vldt, "The environment name must not "
                                   "contain null character.");
    }

    if (nxt_memchr(name->start, '=', name->length) != NULL) {
        return nxt_conf_vldt_error(vldt, "The environment name must not "
                                   "contain '=' character.");
    }

    if (nxt_conf_type(value) != NXT_CONF_STRING) {
        return nxt_conf_vldt_error(vldt, "The \"%V\" environment value must be "
                                   "a string.", name);
    }

    nxt_conf_get_string(value, &str);

    if (nxt_memchr(str.start, '\0', str.length) != NULL) {
        return nxt_conf_vldt_error(vldt, "The \"%V\" environment value must "
                                   "not contain null character.", name);
    }

    return NXT_OK;
}


static nxt_int_t
nxt_conf_vldt_targets_exclusive(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data)
{
    return nxt_conf_vldt_error(vldt, "The \"%s\" option is mutually exclusive "
                               "with the \"targets\" object.", data);
}


static nxt_int_t
nxt_conf_vldt_targets(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    nxt_int_t   ret;
    nxt_uint_t  n;

    n = nxt_conf_object_members_count(value);

    if (n > 254) {
        return nxt_conf_vldt_error(vldt, "The \"targets\" object must not "
                                   "contain more than 254 members.");
    }

    vldt->ctx = data;

    ret = nxt_conf_vldt_object_iterator(vldt, value, &nxt_conf_vldt_target);

    vldt->ctx = NULL;

    return ret;
}


static nxt_int_t
nxt_conf_vldt_target(nxt_conf_validation_t *vldt, nxt_str_t *name,
    nxt_conf_value_t *value)
{
    if (name->length == 0) {
        return nxt_conf_vldt_error(vldt,
                                   "The target name must not be empty.");
    }

    if (nxt_conf_type(value) != NXT_CONF_OBJECT) {
        return nxt_conf_vldt_error(vldt, "The \"%V\" target must be "
                                   "an object.", name);
    }

    return nxt_conf_vldt_object(vldt, value, vldt->ctx);
}


static nxt_int_t
nxt_conf_vldt_clone_namespaces(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value, void *data)
{
    return nxt_conf_vldt_object(vldt, value, data);
}


static nxt_int_t
nxt_conf_vldt_isolation(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    return nxt_conf_vldt_object(vldt, value, data);
}


#if (NXT_HAVE_CLONE_NEWUSER)

typedef struct {
    nxt_int_t container;
    nxt_int_t host;
    nxt_int_t size;
} nxt_conf_vldt_clone_procmap_conf_t;


static nxt_conf_map_t nxt_conf_vldt_clone_procmap_conf_map[] = {
    {
        nxt_string("container"),
        NXT_CONF_MAP_INT32,
        offsetof(nxt_conf_vldt_clone_procmap_conf_t, container),
    },

    {
        nxt_string("host"),
        NXT_CONF_MAP_INT32,
        offsetof(nxt_conf_vldt_clone_procmap_conf_t, host),
    },

    {
        nxt_string("size"),
        NXT_CONF_MAP_INT32,
        offsetof(nxt_conf_vldt_clone_procmap_conf_t, size),
    },

};


static nxt_int_t
nxt_conf_vldt_clone_procmap(nxt_conf_validation_t *vldt, const char *mapfile,
        nxt_conf_value_t *value)
{
    nxt_int_t                           ret;
    nxt_conf_vldt_clone_procmap_conf_t  procmap;

    procmap.container = -1;
    procmap.host = -1;
    procmap.size = -1;

    ret = nxt_conf_map_object(vldt->pool, value,
                              nxt_conf_vldt_clone_procmap_conf_map,
                              nxt_nitems(nxt_conf_vldt_clone_procmap_conf_map),
                              &procmap);
    if (ret != NXT_OK) {
        return ret;
    }

    if (procmap.container == -1) {
        return nxt_conf_vldt_error(vldt, "The %s requires the "
                "\"container\" field set.", mapfile);
    }

    if (procmap.host == -1) {
        return nxt_conf_vldt_error(vldt, "The %s requires the "
                "\"host\" field set.", mapfile);
    }

    if (procmap.size == -1) {
        return nxt_conf_vldt_error(vldt, "The %s requires the "
                "\"size\" field set.", mapfile);
    }

    return NXT_OK;
}


static nxt_int_t
nxt_conf_vldt_clone_uidmap(nxt_conf_validation_t *vldt, nxt_conf_value_t *value)
{
    nxt_int_t  ret;

    if (nxt_conf_type(value) != NXT_CONF_OBJECT) {
        return nxt_conf_vldt_error(vldt, "The \"uidmap\" array "
                                   "must contain only object values.");
    }

    ret = nxt_conf_vldt_object(vldt, value,
                               (void *) nxt_conf_vldt_app_procmap_members);
    if (nxt_slow_path(ret != NXT_OK)) {
        return ret;
    }

    return nxt_conf_vldt_clone_procmap(vldt, "uid_map", value);
}


static nxt_int_t
nxt_conf_vldt_clone_gidmap(nxt_conf_validation_t *vldt, nxt_conf_value_t *value)
{
    nxt_int_t ret;

    if (nxt_conf_type(value) != NXT_CONF_OBJECT) {
        return nxt_conf_vldt_error(vldt, "The \"gidmap\" array "
                                   "must contain only object values.");
    }

    ret = nxt_conf_vldt_object(vldt, value,
                               (void *) nxt_conf_vldt_app_procmap_members);
    if (nxt_slow_path(ret != NXT_OK)) {
        return ret;
    }

    return nxt_conf_vldt_clone_procmap(vldt, "gid_map", value);
}

#endif


static nxt_int_t
nxt_conf_vldt_argument(nxt_conf_validation_t *vldt, nxt_conf_value_t *value)
{
    nxt_str_t  str;

    if (nxt_conf_type(value) != NXT_CONF_STRING) {
        return nxt_conf_vldt_error(vldt, "The \"arguments\" array "
                                   "must contain only string values.");
    }

    nxt_conf_get_string(value, &str);

    if (nxt_memchr(str.start, '\0', str.length) != NULL) {
        return nxt_conf_vldt_error(vldt, "The \"arguments\" array must not "
                                   "contain strings with null character.");
    }

    return NXT_OK;
}


static nxt_int_t
nxt_conf_vldt_php(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    nxt_conf_value_t  *targets;

    static nxt_str_t  targets_str = nxt_string("targets");

    targets = nxt_conf_get_object_member(value, &targets_str, NULL);

    if (targets != NULL) {
        return nxt_conf_vldt_object(vldt, value, nxt_conf_vldt_php_members);
    }

    return nxt_conf_vldt_object(vldt, value,
                                nxt_conf_vldt_php_notargets_members);
}


static nxt_int_t
nxt_conf_vldt_php_option(nxt_conf_validation_t *vldt, nxt_str_t *name,
    nxt_conf_value_t *value)
{
    if (name->length == 0) {
        return nxt_conf_vldt_error(vldt,
                                   "The PHP option name must not be empty.");
    }

    if (nxt_conf_type(value) != NXT_CONF_STRING) {
        return nxt_conf_vldt_error(vldt, "The \"%V\" PHP option must be "
                                   "a string.", name);
    }

    return NXT_OK;
}


#if (NXT_HAVE_NJS)

static nxt_int_t
nxt_conf_vldt_js_module(nxt_conf_validation_t *vldt, nxt_conf_value_t *value,
    void *data)
{
    if (nxt_conf_type(value) == NXT_CONF_ARRAY) {
        return nxt_conf_vldt_array_iterator(vldt, value,
                                            &nxt_conf_vldt_js_module_element);
    }

    /* NXT_CONF_STRING */

    return nxt_conf_vldt_js_module_element(vldt, value);
}


static nxt_int_t
nxt_conf_vldt_js_module_element(nxt_conf_validation_t *vldt,
    nxt_conf_value_t *value)
{
    nxt_str_t         name;
    nxt_conf_value_t  *module;

    if (nxt_conf_type(value) != NXT_CONF_STRING) {
        return nxt_conf_vldt_error(vldt, "The \"js_module\" array must "
                                   "contain only string values.");
    }

    nxt_conf_get_string(value, &name);

    module = nxt_script_info_get(&name);
    if (module == NULL) {
        return nxt_conf_vldt_error(vldt, "JS module \"%V\" is not found.",
                                   &name);
    }

    return NXT_OK;
}

#endif
