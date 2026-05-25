# -*- mode: python ; coding: utf-8 -*-

import os

playwright_browsers = os.path.join(os.environ['LOCALAPPDATA'], 'ms-playwright')

a = Analysis(
    ['pan_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(playwright_browsers, 'chromium-1208'), 'ms-playwright/chromium-1208'),
        (os.path.join(playwright_browsers, 'chromium_headless_shell-1208'), 'ms-playwright/chromium_headless_shell-1208'),
        (os.path.join(playwright_browsers, 'ffmpeg-1011'), 'ms-playwright/ffmpeg-1011'),
    ],
    hiddenimports=['playwright', 'playwright.sync_api'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PAN Lookup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PAN Lookup',
)
