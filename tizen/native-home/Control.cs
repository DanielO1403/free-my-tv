using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.RegularExpressions;

// One-shot native Home helper for Free My TV on Samsung TVs.
//
// Samsung has no public API for the remote's Home key. On the TVs this was tested against, the Home key follows
// app_operation_set_current_app(".../main", appId), and the boot manager reads db/appfw/home_appid plus the Smart Hub
// auto_start setting. This helper changes exactly those values, after saving every value it touches, and restores them
// on request. It never requests root and never changes security policy.
//
// It runs as the TV's SDK user (UID 901), 32-bit, through the one-shot SDB transport in run.py. It is not part of the
// app and does not stay running.
class Control {
  const string Operation = "http://tizen.org/appcontrol/operation/main";
  const string Target = "FreeMyTVio.FreeMyTV";
  const string Package = "FreeMyTVio";
  const string AppDir = "/opt/usr/apps/" + Package;
  static readonly string[] Keys = {
    "db/appfw/home_appid",
    "db/appfw/startup_appid",
    "db/appfw/booting_appid_backup",
    "db/first_screen/type"
  };
  const string AutoKey = "db/menu/smart_hub/ontvsetting/auto_start";

  [DllImport("libbundle.so.0")] static extern IntPtr bundle_create();
  [DllImport("libbundle.so.0")] static extern void bundle_free(IntPtr b);
  [DllImport("libaul.so.0")] static extern int aul_svc_set_operation(IntPtr b, string op);
  [DllImport("libaul.so.0")] static extern int aul_get_default_app(IntPtr b, out IntPtr app);
  [DllImport("libapp-context-manager-common.so")] static extern byte util_is_appbooting_supported_webapp_byappid(string app);
  [DllImport("libcapi-appfw-app-operation-tv.so.0")] static extern int app_operation_set_current_app(string op, string app);
  [DllImport("libvconf.so.0")] static extern int vconf_set_str(string key, string value);
  [DllImport("libvconf.so.0")] static extern IntPtr vconf_get_str(string key);
  [DllImport("libvconf.so.0")] static extern int vconf_unset(string key);
  [DllImport("libvconf.so.0")] static extern int vconf_set_int(string key, int value);
  [DllImport("libvconf.so.0")] static extern int vconf_get_int(string key, out int value);
  [DllImport("libc")] static extern uint getuid();
  [DllImport("libc")] static extern void free(IntPtr ptr);

  static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions { WriteIndented = false };

  public class Snapshot {
    public string Home { get; set; }
    public Dictionary<string, string> Strings { get; set; }
    public int Autostart { get; set; }
    public uint Uid { get; set; }
    public int BootSupported { get; set; }
    public int AppInstalled { get; set; }
    public int PointerSize { get; set; }
    public string Model { get; set; }
    public string Firmware { get; set; }
    public string Tizen { get; set; }
    public string Runtime { get; set; }
    public string SavedAt { get; set; }
  }

  static string ReadString(string key) {
    IntPtr p = vconf_get_str(key);
    if (p == IntPtr.Zero) return null;   // the key does not exist on this TV
    try { return Marshal.PtrToStringAnsi(p) ?? ""; } finally { free(p); }
  }

  static string Home() {
    IntPtr b = bundle_create();
    if (b == IntPtr.Zero) throw new Exception("Cannot create the app-control bundle");
    try {
      if (aul_svc_set_operation(b, Operation) != 0) throw new Exception("Cannot set the Home query operation");
      IntPtr p;
      if (aul_get_default_app(b, out p) != 0 || p == IntPtr.Zero) throw new Exception("Cannot read the Home operation");
      try { return Marshal.PtrToStringAnsi(p) ?? ""; } finally { free(p); }
    } finally { bundle_free(b); }
  }

  static string Prd(string name) {
    try {
      foreach (string line in File.ReadAllLines("/etc/prd_info.ini")) {
        string text = line.Trim();
        if (text.StartsWith(name + "=", StringComparison.Ordinal))
          return text.Substring(name.Length + 1).Trim().TrimEnd(';');
      }
    } catch (Exception) { }
    return "";
  }

  static string TizenText() {
    try { return File.ReadAllText("/etc/tizen-release").Trim(); } catch (Exception) { return ""; }
  }

  static int TizenMajor(string text) {
    Match m = Regex.Match(text ?? "", @"(\d+)\.");
    return m.Success ? int.Parse(m.Groups[1].Value) : 0;
  }

  static int BootSupported() {
    try { return util_is_appbooting_supported_webapp_byappid(Target) != 0 ? 1 : 0; } catch (Exception) { return -1; }
  }

  static Snapshot Query() {
    var s = new Snapshot {
      Strings = new Dictionary<string, string>(),
      Uid = getuid(),
      BootSupported = BootSupported(),
      AppInstalled = Directory.Exists(AppDir) ? 1 : 0,
      PointerSize = IntPtr.Size,
      Model = Prd("Model"),
      Firmware = Prd("Version"),
      Tizen = TizenText(),
      Runtime = RuntimeInformation.FrameworkDescription
    };
    s.Home = Home();
    foreach (string key in Keys) s.Strings[key] = ReadString(key);
    int auto;
    if (vconf_get_int(AutoKey, out auto) != 0) throw new Exception("Cannot read " + AutoKey);
    s.Autostart = auto;
    return s;
  }

  static void SetString(string key, string value) {
    if (value == null) {
      if (ReadString(key) == null) return;   // it was absent, and it still is
      if (vconf_unset(key) != 0) throw new Exception("Cannot remove " + key);
      if (ReadString(key) != null) throw new Exception("Readback failed (key still exists) for " + key);
      return;
    }
    if (vconf_set_str(key, value) != 0) throw new Exception("Cannot write " + key);
    string got = ReadString(key);
    if (got != value) throw new Exception("Readback failed for " + key + ": " + got);
  }

  static void SetAuto(int value) {
    if (vconf_set_int(AutoKey, value) != 0) throw new Exception("Cannot write " + AutoKey);
    int got;
    if (vconf_get_int(AutoKey, out got) != 0 || got != value) throw new Exception("Readback failed for " + AutoKey);
  }

  static void SetHome(string value) {
    if (app_operation_set_current_app(Operation, value) != 0) throw new Exception("Cannot set the Home operation");
    string got = Home();
    if (got != value) throw new Exception("Home readback failed: " + got);
  }

  static void Restore(Snapshot s) {
    SetHome(s.Home);
    foreach (string key in Keys) SetString(key, s.Strings[key]);
    SetAuto(s.Autostart);
  }

  static void VerifyRestored(Snapshot s) {
    Snapshot now = Query();
    if (now.Home != s.Home) throw new Exception("Home did not return to " + s.Home);
    foreach (string key in Keys)
      if (now.Strings[key] != s.Strings[key]) throw new Exception("Did not restore " + key);
    if (now.Autostart != s.Autostart) throw new Exception("Did not restore " + AutoKey);
  }

  static void CheckSnapshot(Snapshot s) {
    if (s == null || string.IsNullOrWhiteSpace(s.Home) || s.Strings == null || s.Strings.Count != Keys.Length ||
        (s.Autostart != 0 && s.Autostart != 1))
      throw new Exception("Invalid original snapshot");
    foreach (string key in Keys) {
      string value;
      if (!s.Strings.TryGetValue(key, out value))
        throw new Exception("Missing original setting: " + key);
    }
    if (string.IsNullOrWhiteSpace(s.Strings["db/appfw/home_appid"]))
      throw new Exception("Missing the original Home setting");
    if (s.Home == Target || s.Strings["db/appfw/home_appid"] == Target)
      throw new Exception("This snapshot is the applied state, not the original; restore the original baseline first");
    string model = Prd("Model");
    if (!string.IsNullOrWhiteSpace(s.Model) && !string.IsNullOrWhiteSpace(model) && s.Model != model)
      throw new Exception("Snapshot is from " + s.Model + ", but this TV is " + model);
  }

  static void CheckEnvironment(bool apply) {
    if (IntPtr.Size != 4) throw new Exception("Expected the TV's 32-bit runtime, got " + IntPtr.Size * 8 + "-bit");
    uint uid = getuid();
    if (uid != 901) throw new Exception("Expected the TV's SDK user (UID 901), got " + uid);
    if (!apply) return;
    if (!Directory.Exists(AppDir)) throw new Exception("Free My TV is not installed at " + AppDir);
    int supported = BootSupported();
    if (supported == 0) throw new Exception("The installed Free My TV is not eligible for boot on this TV");
    if (supported < 0) throw new Exception("The TV did not answer the boot-eligibility check");
    int major = TizenMajor(TizenText());
    if (major > 0 && major < 6) throw new Exception("This helper expects Tizen 6 or newer; the TV reports Tizen " + major);
  }

  static void Apply(Snapshot original) {
    Snapshot before = Query();
    if (before.Home != original.Home && before.Home != Target)
      throw new Exception("The TV's Home app changed since the snapshot (" + before.Home + "); stop for review");
    if (before.Autostart != original.Autostart && before.Autostart != 1)
      throw new Exception("The TV's startup setting changed since the snapshot; stop for review");
    foreach (string key in Keys) {
      string value = before.Strings[key], saved = original.Strings[key];
      bool mayBeTarget = key == "db/appfw/home_appid" || key == "db/appfw/startup_appid" ||
                         key == "db/appfw/booting_appid_backup";
      if (value != saved && !(mayBeTarget && value == Target))
        throw new Exception("The TV's " + key + " changed since the snapshot; stop for review");
    }
    try {
      SetHome(Target);
      SetString("db/appfw/home_appid", Target);
      SetAuto(1);
      Snapshot after = Query();
      if (after.Home != Target || after.Strings["db/appfw/home_appid"] != Target || after.Autostart != 1)
        throw new Exception("The TV did not keep the new Home/startup values");
      Console.WriteLine("FMTV_HOME_APPLIED=" + JsonSerializer.Serialize(after, JsonOptions));
    } catch (Exception) {
      try {
        Restore(original);
        Console.Error.WriteLine("Original Home/startup values restored after the failed apply.");
      } catch (Exception restoreError) {
        Console.Error.WriteLine("Restore after the failed apply also failed: " + restoreError.Message);
      }
      throw;
    }
  }

  static int Main(string[] args) {
    try {
      if (args.Length == 1 && args[0] == "query") {
        Console.WriteLine("FMTV_HOME_JSON=" + JsonSerializer.Serialize(Query(), JsonOptions));
        return 0;
      }
      if (args.Length != 2 || (args[0] != "apply" && args[0] != "restore"))
        throw new Exception("Use query, apply SNAPSHOT, or restore SNAPSHOT");
      Snapshot original = JsonSerializer.Deserialize<Snapshot>(File.ReadAllText(args[1]), JsonOptions);
      CheckSnapshot(original);
      if (args[0] == "restore") {
        CheckEnvironment(false);
        Restore(original);
        VerifyRestored(original);
        Console.WriteLine("FMTV_HOME_RESTORED=" + JsonSerializer.Serialize(Query(), JsonOptions));
        return 0;
      }
      CheckEnvironment(true);
      Apply(original);
      return 0;
    } catch (Exception e) {
      Console.Error.WriteLine(e.ToString());
      return 1;
    }
  }
}
