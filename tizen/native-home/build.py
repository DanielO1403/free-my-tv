#!/usr/bin/env python3
"""Builds the one-shot native Home helper (FreeMyTVHomeControl.dll) for the TV.

    python3 tizen/native-home/build.py

Needs the .NET SDK 6 or newer (https://dotnet.microsoft.com/download). The DLL is framework-dependent and targets
.NET 6, which the 2024 Samsung TVs have. The output stays in out/native-home/ (ignored by git); run.py copies it to the
TV when you query, apply or restore.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'out', 'native-home')
PROJECT = os.path.join(HERE, 'Control.csproj')
FILES = ('FreeMyTVHomeControl.dll', 'FreeMyTVHomeControl.runtimeconfig.json', 'FreeMyTVHomeControl.deps.json')


def main():
    dotnet = shutil.which('dotnet')
    if not dotnet:
        sys.exit('The .NET SDK is not installed. Install .NET 6 or newer from https://dotnet.microsoft.com/download, '
                 'then run this again.')
    os.makedirs(OUT, exist_ok=True)
    run = subprocess.run([dotnet, 'build', PROJECT, '-c', 'Release', '-o', OUT, '--nologo',
                          '-p:UseAppHost=false'], cwd=ROOT)
    if run.returncode:
        sys.exit('dotnet build failed.')
    missing = [name for name in FILES if not os.path.exists(os.path.join(OUT, name))]
    if missing:
        sys.exit('The build finished without: ' + ', '.join(missing))
    print('Built %s (%d KB).' % (os.path.join('out', 'native-home', FILES[0]),
                                 os.path.getsize(os.path.join(OUT, FILES[0])) // 1024))


if __name__ == '__main__':
    main()
