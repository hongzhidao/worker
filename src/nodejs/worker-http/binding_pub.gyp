{
    'targets': [{
        'target_name': "worker-http",
        'cflags!': [ '-fno-exceptions' ],
        'cflags_cc!': [ '-fno-exceptions' ],
        'conditions': [
            ['OS=="mac"', {
              'xcode_settings': {
                'GCC_ENABLE_CPP_EXCEPTIONS': 'YES'
              }
            }]
        ],
        'sources': ["worker.cpp", "addon.cpp"],
        'libraries': ["-lworker"]
    }]
}
