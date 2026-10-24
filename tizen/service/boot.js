/*
 * Free My TV's background service on Samsung (Tizen): opens the home screen when the TV turns on.
 * Declared in config.xml with on-boot, so it starts with the TV. Most Samsung TVs don't really power off: they sleep
 * ("Instant On"), and while they sleep this service's timers stop too. So a tick that comes much later than it should
 * means the TV just woke up, and the home screen opens again.
 */
var APP = 'FreeMyTVio.FreeMyTV';
var TICK = 5000;      // how often the service checks the clock
var SLEPT = 30000;    // a gap this long between ticks means the TV was asleep
var DELAY = 4000;     // after waking, give the TV's own start screen a moment before opening ours

var timer = null, last = 0;

function open() {
  try {
    tizen.application.launch(APP, function () {}, function (e) { console.log('Free My TV: launch failed ' + e.message); });
  } catch (e) {
    console.log('Free My TV: launch threw ' + e.message);
  }
}

function tick() {
  var now = Date.now();
  if (last && now - last > SLEPT) setTimeout(open, DELAY);
  last = now;
}

module.exports.onStart = function () {
  setTimeout(open, DELAY);
  last = Date.now();
  timer = setInterval(tick, TICK);
};

module.exports.onRequest = function () {};

module.exports.onExit = function () {
  if (timer) clearInterval(timer);
};
