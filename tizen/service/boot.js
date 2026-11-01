/*
 * Eden's background service on Samsung (Tizen).
 *
 * It has two jobs:
 *  1. If the TV starts the service at boot (`on-boot="true"` in config.xml), open Eden after the TV's own start
 *     screen has settled. This is a fallback for TVs that do not run the native Home assignment.
 *  2. Stay alive while the TV is on. Most Samsung TVs sleep ("Instant On") instead of powering off, and the service's
 *     timers stop while they sleep. A tick that arrives much later than expected means the TV just woke, so Eden is
 *     opened again. A screen-state listener does the same on TVs that expose it.
 *
 * The native Home assignment (tizen/native-home) is still the only way to make the physical Home key return to Eden.
 * This service cannot take the Home key. A small status page on 127.0.0.1:8093 lets the home screen show what happened.
 */
var APP = 'FreeMyTVio.FreeMyTV';
var SERVICE = 'FreeMyTVio.Boot';
var TICK = 5000;       // how often the service checks the clock
var SLEPT = 15000;     // a gap this long between ticks (3 missed ticks) means the TV was asleep
var DELAY = 4000;      // after waking, give the TV's own start screen a moment before opening Eden
var BOOT_DELAY = 9000; // after a cold boot, let Samsung's start screen and native Home settle first
var MIN_GAP = 8000;    // don't launch twice in a row
var PORT = 8093;

var timer = null, bootTimer = null, server = null, screenListener = false;
var last = 0, lastWake = 0, lastOpen = 0;
var state = {
  started: 0, wakes: 0, launches: 0, skipped: 0, errors: 0,
  error: '', screen: '', lastLaunch: 0, boot: false
};

function running(done) {
  try {
    if (!tizen.application.getAppsContext) { done(false); return; }
    tizen.application.getAppsContext(function (contexts) {
      for (var i = 0; contexts && i < contexts.length; i++) {
        if (contexts[i].appId === APP) { done(true); return; }
      }
      done(false);
    }, function () { done(false); });
  } catch (e) {
    done(false);
  }
}

function launch() {
  var now = Date.now();
  if (lastOpen && now - lastOpen < MIN_GAP) { state.skipped++; return; }
  lastOpen = now;
  try {
    // The 'boot' flag lets the home screen step aside when the Xbox is what woke the TV (web/home.js, xboxCheck).
    var control = new tizen.ApplicationControl('http://freemytv.io/appcontrol/operation/resume', null, null, null,
        [new tizen.ApplicationControlData('fmtv', ['boot'])]);
    tizen.application.launchAppControl(control, APP, function () {
      state.launches++; state.lastLaunch = Date.now(); state.error = '';
    }, function (e) {
      state.error = 'launchAppControl: ' + e.name + ' ' + e.message;
      try {
        tizen.application.launch(APP, function () {
          state.launches++; state.lastLaunch = Date.now();
        }, function (e2) {
          state.errors++; state.error += ' / launch: ' + e2.message;
        });
      } catch (e3) {
        state.errors++; state.error += ' / launch: ' + e3.message;
      }
    });
  } catch (e) {
    state.errors++; state.error = 'open: ' + e.message;
  }
}

function open(reason, onlyIfNotRunning) {
  if (onlyIfNotRunning) {
    running(function (isRunning) {
      if (isRunning) { state.skipped++; return; }
      launch();
    });
    return;
  }
  launch();
}

function tick() {
  var now = Date.now();
  if (last && now - last > SLEPT) {
    state.wakes++;
    lastWake = now;
    setTimeout(function () { open('timer'); }, DELAY);
  }
  last = now;
}

function screenChanged(previous, current) {
  state.screen = current;
  var normal = current === 'SCREEN_NORMAL' || (tizen.power && current === tizen.power.SCREEN_NORMAL);
  var wasNormal = previous === 'SCREEN_NORMAL' || (tizen.power && previous === tizen.power.SCREEN_NORMAL);
  if (normal && !wasNormal) {
    var now = Date.now();
    if (!lastWake || now - lastWake > 3000) {
      state.wakes++;
      lastWake = now;
      setTimeout(function () { open('screen'); }, DELAY);
    }
  }
}

module.exports.onStart = function () {
  state.started = Date.now();
  state.boot = true;
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
    state.errors++;
    state.error = 'status page: ' + e.message;
  }
  try {
    if (tizen.power && tizen.power.setScreenStateChangeListener) {
      tizen.power.setScreenStateChangeListener(screenChanged);
      screenListener = true;
      try { state.screen = tizen.power.getScreenState(); } catch (e) {}
    }
  } catch (e2) {
    state.error = (state.error ? state.error + ' / ' : '') + 'screen listener: ' + e2.message;
  }
  bootTimer = setTimeout(function () { open('boot', true); }, BOOT_DELAY);
};

module.exports.onRequest = function () {};

module.exports.onExit = function () {
  if (timer) clearInterval(timer);
  if (bootTimer) clearTimeout(bootTimer);
  if (screenListener) {
    try { tizen.power.unsetScreenStateChangeListener(); } catch (e) {}
  }
  try { if (server) server.close(); } catch (e2) {}
};
