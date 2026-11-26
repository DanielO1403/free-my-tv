# WWW → HDMI 3 on a Samsung TV

The WWW/Internet key is not a normal remote key: the TV's own Internet app (`org.tizen.browser`) runs in the
background from power-on and grabs it. Two things make it open HDMI 3 instead:

1. **A key rule.** A tiny native carrier package (`wwwkey.tpk`) registers
   `XF86WWW → org.tizen.tv-viewer` with the same arguments Samsung's own HDMI 3 rule uses. Tizen only reads
   `<app-context>` rules from TPK manifests, so this has to be a native package, not the web app.

2. **The Internet app stopped.** While `org.tizen.browser` runs, it also takes the key, so the two handlers race
   (HDMI 3 sometimes, Internet sometimes). Deactivating the Internet app for the TV's user leaves the key rule
   alone, and WWW opens HDMI 3 every time.

## The rule

`tizen-manifest.xml` in this folder is the carrier's manifest. Its rule:

```xml
<app-context appid="FreeMyTVioWWW.Key">
  <app-context-rule>
    <source selector="key">XF86WWW</source>
    <target selector="app" request="launch"
            args="discrete:XF86DiscretHDMI3 set_source_before_visible:1 __K_EX_FORCE_BOOST:enable">org.tizen.tv-viewer</target>
  </app-context-rule>
</app-context>
```

The `exec` points at an empty native stub; the service is never started. Sign the TPK with TizenBrew Installer and
install it once. Verify the row on the TV:

```sh
sqlite3 /opt/dbspace/.app-context.db "select * from key_filter where key='XF86WWW'"
```

## Stop the Internet app

Run once on the TV (SDB shell as the `sdk` user), for the TV's app user (`5001` on this set):

```sh
pkgcmd -D -t tpk -n org.tizen.browser --uid 5001
```

Undo it with:

```sh
pkgcmd -A -t tpk -n org.tizen.browser --uid 5001
```

Uninstalling the carrier package removes its rule; WWW then falls back to the Internet app (if re-activated).
