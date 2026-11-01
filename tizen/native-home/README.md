# Samsung Home and startup

This folder is a **one-time, optional helper** for Samsung TVs. It makes Eden (Free My TV) the app that the remote's
**Home** key opens and the app the TV starts when it powers on.

A `.wgt` cannot do either job by itself. Samsung gives apps no public API for the physical Home key, and it ignores an
app's request to run at boot on most retail certificates. The reliable route on Tizen 6 and newer is Samsung's own
native Home assignment:

- the `http://tizen.org/appcontrol/operation/main` operation points at Eden;
- `db/appfw/home_appid` points at Eden;
- `db/menu/smart_hub/ontvsetting/auto_start` is `1`.

The helper sets exactly those values, saves the original values first, reads every write back, and puts the originals
back on `restore`. It does not request root, does not change security policy, and does not stay running on the TV.

> This is a separate device operation. Read this page, run `query` first, and keep the snapshot it saves. Do not run
> `apply` on a TV you cannot restore.

## What you need

- A Samsung TV from 2017 or newer, in **Developer Mode**, with this computer's IP in **Host PC IP** and the TV
  restarted. On 2023 and newer TVs the app must already be installed and signed for that TV (TizenBrew does this).
- Eden installed with the package id `FreeMyTVio` (the app id is `FreeMyTVio.FreeMyTV`). The helper refuses another
  package.
- Python 3 on this computer, and the TV and computer on the same network.
- The .NET SDK 6 or newer **only to build the helper**. The TV runs the compiled helper; the SDK stays on the computer.

## Build the helper

```bash
python3 tizen/native-home/build.py
```

It writes three files to `out/native-home/` (ignored by git):

```text
FreeMyTVHomeControl.dll
FreeMyTVHomeControl.runtimeconfig.json
FreeMyTVHomeControl.deps.json
```

`run.py` copies them to the TV each time. If the TV's .NET runtime is missing, `query` says so; nothing is changed.

## Query first (read-only)

```bash
python3 tizen/native-home/run.py 192.168.1.50 query
```

`query` only reads the TV's Home assignment and the four related settings, and stages the helper in the TV's SDK
temporary folder. It prints the model, firmware, Tizen version, Home app, the saved keys, whether Eden is installed,
whether the TV says Eden is eligible for boot, and the user/runtime the helper sees.

On a healthy Tizen 9 Q8F the output looks like this (values differ by TV):

```text
TV: QN55Q8FAAK, firmware T-...
Tizen: Tizen 9.0 ...
Home app: com.samsung.tv.csfs
  db/appfw/home_appid = com.samsung.tv.csfs
  db/appfw/startup_appid = org.tizen.tv-viewer
  db/appfw/booting_appid_backup = org.tizen.tv-viewer
  db/first_screen/type = com.samsung.tv.csfs
  db/menu/smart_hub/ontvsetting/auto_start = 0
Free My TV installed: yes; boot eligible: yes; SDK user: 901; runtime: ...
```

The first `query` saves the original values to `tizen/native-home/.state/original.json`. **Keep that file.** It is
ignored by git and is the only exact rollback baseline. `query` never overwrites an existing snapshot.

If the TV says `boot eligible: no`, or `Home app` is already `FreeMyTVio.FreeMyTV`, stop. Do not apply. A snapshot is
only valid when it was taken before the assignment.

## Apply

```bash
python3 tizen/native-home/run.py 192.168.1.50 apply
```

It shows the current values, the three changes, and asks you to type `APPLY`. Then it:

1. re-reads the TV and refuses if any value changed since the snapshot;
2. checks the TV's model, Tizen version, SDK user, 32-bit runtime, installed package, and boot eligibility;
3. sets the Home operation, `home_appid`, and `auto_start=1`;
4. reads all three back;
5. restores the snapshot automatically if any step fails.

Restart the TV. It should start into Eden, and the remote's Home key should open Eden from another app.

`--yes` skips the confirmation for scripted use. Do not use it until you have read the current values and have a
snapshot.

## Restore

```bash
python3 tizen/native-home/run.py 192.168.1.50 restore
```

It shows the saved original values, asks you to type `RESTORE`, writes them back, reads them back, and reports the
result. Run this **before** uninstalling Eden or changing its package/app id. If you leave Eden assigned as Home and
then uninstall it, Samsung's Home key has nowhere to go.

## How it works

`run.py` speaks SDB directly (like `tizen/install.py`), so it does not need Samsung's `sdb` or Tizen Studio. It stages
the helper in `/home/owner/share/tmp/sdk_tools` and runs it through the TV's `0 appinstall tpk` filename handling as
the SDK user (UID 901). The helper is a short-lived .NET program; it calls the TV's own native libraries:

| Library | Call | Purpose |
|---|---|---|
| `libaul.so.0` | `aul_get_default_app` | read the current Home app |
| `libcapi-appfw-app-operation-tv.so.0` | `app_operation_set_current_app` | set the Home app |
| `libvconf.so.0` | `vconf_get_str`, `vconf_set_str`, `vconf_get_int`, `vconf_set_int` | read and write the settings |
| `libapp-context-manager-common.so` | `util_is_appbooting_supported_webapp_byappid` | ask whether Eden may run at boot |

The helper refuses to run unless it is the TV's 32-bit SDK user (UID 901), the package is installed at
`/opt/usr/apps/FreeMyTVio`, and the TV reports Tizen 6 or newer. It also refuses a snapshot whose model differs from
the TV's.

The four saved string keys are:

```text
db/appfw/home_appid
db/appfw/startup_appid
db/appfw/booting_appid_backup
db/first_screen/type
```

plus `db/menu/smart_hub/ontvsetting/auto_start` (integer). A key that does not exist on the TV is saved as `(absent)`
and `restore` removes it again with `vconf_unset`, so an absent `startup_appid` (common on newer TVs) is a valid
baseline. The helper only changes the Home operation, `home_appid`, and `auto_start`; the other values are saved so
`restore` can put back the exact baseline after Samsung's boot manager updates the derived startup keys.

## The boot service (fallback)

`tizen/config.xml` also declares `FreeMyTVio.Boot` with `on-boot="true"` and `auto-restart="true"`. The service opens
Eden after the TV's start screen settles, and reopens it after sleep/wake. This is only a fallback:

- Samsung may rewrite `on-boot`/`auto-restart` to false for public certificates;
- the service cannot take the Home key;
- the native assignment above is what makes power-on and Home reliable.

The service's status is available at `http://127.0.0.1:8093/` on the TV; **Free My TV → Home Settings → Startup
check** shows it.

## Troubleshooting

- **`The TV did not run the helper`** — Developer Mode is off, **Host PC IP** is not this computer, the TV was not
  restarted after enabling Developer Mode, the two devices are on different networks, or a firewall blocks the
  callback. Fix that, then run `query` again.
- **`The native helper is not built`** — run `python3 tizen/native-home/build.py`.
- **`The TV's Home app changed since the snapshot`** — someone changed the Home app or the TV's settings after the
  snapshot. Run `query`, compare, and decide whether the old snapshot is still valid. Do not force it.
- **`This TV already uses Free My TV as its Home app`** — the assignment is already applied. Keep the earlier
  snapshot; use `restore` before uninstalling.
- **`boot eligible: no`** — the TV does not accept Eden as a boot app. Do not apply; the Home key can still be
  assigned, but startup would be unreliable. Check that the installed app is the signed package for this TV.
- **`Expected the TV's SDK user (UID 901)`** — the helper was not started through the reviewed SDB route. Nothing was
  changed.
- **A write fails and restore also fails** — stop. Do not uninstall anything. Note the exact error and the snapshot
  file; the TV's Home app may need to be set back on the TV or with Samsung's tools.

## If you no longer want it

```bash
python3 tizen/native-home/run.py 192.168.1.50 restore
```

Then uninstall Eden normally. The snapshot can stay for reference; it contains no keys or personal data beyond the
TV's model/firmware and the original app ids.

## Evidence and limits

The native route was verified on a 2024 Samsung Frame and an S90D running firmware 2130.0 / Tizen 9, and the same
`home_appid` + `auto_start=1` mechanism is documented for Tizen 9. The QN55Q8FAAK is a 2025 Q8F on Tizen 9, so this
is the intended route, but **this exact model has not been tested here**. Run `query` first and treat the output as
the authority. Firmware updates can change these keys; re-run `query` after a major update.

The helper deliberately has no root path, no SQL, no security-policy changes, and no persistent daemon. Its only
writes are the Home operation, `db/appfw/home_appid`, and `auto_start`.
