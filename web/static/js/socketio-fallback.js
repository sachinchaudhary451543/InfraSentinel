/*
 * Socket.IO compatibility fallback.
 *
 * The production deployment should replace this with the official bundled
 * socket.io-client distribution. It intentionally provides the small event API
 * used by the UI so pages continue to use their REST polling paths when a
 * realtime client is not bundled or is unavailable offline.
 */
(function (global) {
  "use strict";

  if (typeof global.io === "function") return;

  function createSocket() {
    var handlers = Object.create(null);
    return {
      connected: false,
      on: function (event, callback) {
        (handlers[event] || (handlers[event] = [])).push(callback);
        return this;
      },
      off: function (event, callback) {
        if (!handlers[event]) return this;
        handlers[event] = callback
          ? handlers[event].filter(function (handler) {
              return handler !== callback;
            })
          : [];
        return this;
      },
      once: function (event, callback) {
        var socket = this;
        function onceHandler() {
          socket.off(event, onceHandler);
          callback.apply(null, arguments);
        }
        return socket.on(event, onceHandler);
      },
      emit: function () {
        return this;
      },
      disconnect: function () {
        return this;
      },
    };
  }

  global.io = createSocket;
})(window);
