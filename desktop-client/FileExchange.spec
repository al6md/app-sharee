# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec File for FileExchangeSetup.exe / share coc.exe
"""
block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('gdrive_credentials.json', '.')
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'requests',
        'sqlite3',
        'winreg',
        'icon_provider',
        'theme',
        'access_hub_widget',
        'local_bridge',
        'supabase_client',
        'sync_engine',
        'offline_queue',
        'office_handler',
        'lan_sync',
        'gui',
        'conflict_manager',
        'autostart',
        'windows_integration',
        'gdrive_client',
        'gdrive_sync_service',
        'google.oauth2.credentials',
        'googleapiclient',
        'googleapiclient.discovery',
        'googleapiclient.http',
        'googleapiclient.model',
        'google_auth_httplib2',
        'httplib2'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'boto3', 'botocore', 's3transfer', 'r2_client'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='share coc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='assets/logo.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version_info=None
)
