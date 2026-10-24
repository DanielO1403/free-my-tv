/*
 * Eden's background service on Samsung (Tizen): opens the home screen when the TV wakes up.
 * The home screen starts it (web/tv.js, bootService) the way TizenBrew starts its own service; it then keeps running
 * while the TV is on and in standby. Most Samsung TVs don't really power off: they sleep ("Instant On"), and while
 * they sleep this service's timers stop too. So a tick that comes much later than it should means the TV just woke
 * up, and the home screen opens again. A small status page on 127.0.0.1:8093 lets the home screen see it running.
 */
var APP = 'FreeMyTVio.FreeMyTV';
var TICK = 5000;      // how often the service checks the clock
var SLEPT = 15000;    // a gap this long between ticks (3 missed ticks) means the TV was asleep
var DELAY = 4000;     // after waking, give the TV's own start screen a moment before opening ours
var PORT = 8093;

var timer = null, last = 0, server = null;
var state = {started: 0, wakes: 0, launches: 0, error: ''};

function open() {
  try {
    // The 'boot' flag lets the home screen step aside when the Xbox is what woke the TV (web/home.js, xboxCheck).
    var control = new tizen.ApplicationControl('http://tizen.org/appcontrol/operation/default', null, null, null,
        [new tizen.ApplicationControlData('fmtv', ['boot'])]);
    tizen.application.launchAppControl(control, APP, function () { state.launches++; }, function (e) {
      state.error = 'launchAppControl: ' + e.name + ' ' + e.message;
      try { tizen.application.launch(APP, function () { state.launches++; }, function (e2) { state.error += ' / launch: ' + e2.message; }); } catch (e3) {}
    });
  } catch (e) {
    state.error = 'open: ' + e.message;
  }
}

function tick() {
  var now = Date.now();
  if (last && now - last > SLEPT) { state.wakes++; setTimeout(open, DELAY); }
  last = now;
}

module.exports.onStart = function () {
  state.started = Date.now();
  last = Date.now();
  timer = setInterval(tick, TICK);
  try {
    server = require('http').createServer(function (req, res) {
      res.writeHead(200, {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'});
      res.end(JSON.stringify(state));
    });
    server.on('error', function () {});
    server.listen(PORT, '127.0.0.1');
  } catch (e) {
    state.error = 'status page: ' + e.message;
  }
};

module.exports.onRequest = function () {};

module.exports.onExit = function () {
  if (timer) clearInterval(timer);
  try { if (server) server.close(); } catch (e) {}
};
