// can only be ran as part of a --require param on the node process
if (module.parent && module.parent.id === "internal/preload") {
    const { Module } = require("module")

    if (!Module.prototype.require.__worker_loader) {
        const http = require("./http")
        const websocket = require("./websocket")

        const original = Module.prototype.require;

        Module.prototype.require = function (id) {
            switch(id) {
                case "http":
                case "worker-http":
                    return http

                case "websocket":
                case "worker-http/websocket":
                    return websocket
            }

            return original.apply(this, arguments);
        }

        Module.prototype.require.__worker_loader = true;
    }
}
