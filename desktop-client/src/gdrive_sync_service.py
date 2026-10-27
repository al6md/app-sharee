# -*- coding: utf-8 -*-
"""
خدمة المزامنة السحابية لـ Google Drive
تستخدم GoogleDriveClient الموحد مع دعم كامل للمجلدات الفرعية المتداخلة
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from gdrive_client import GoogleDriveClient, DEFAULT_ROOT_FOLDER_ID


class GoogleDriveSyncDaemon:
    def __init__(self, root_folder_id=None):
        self.sync_dir = Path.home() / "FileExchangeShared"
        self.client = GoogleDriveClient(root_folder_id=root_folder_id or DEFAULT_ROOT_FOLDER_ID)
        self.client.sync_folder = self.sync_dir
        self.root_folder_id = self.client.root_folder_id
        self.service = self.client.service

    def refresh_folders(self):
        return self.client.refresh_folders(force=True)

    def get_or_create_folder(self, folder_name):
        return self.client.ensure_folder(folder_name)

    def upload_local_file(self, file_path):
        return self.client.upload_file(str(file_path))

    def pull_cloud_updates(self):
        snap = self.client.snapshot(force=True)
        if snap is None:
            return
        for rel_folder in sorted(snap.folders):
            if rel_folder:
                (self.sync_dir / rel_folder).mkdir(parents=True, exist_ok=True)
        for rel_file, meta in snap.files.items():
            dest = self.sync_dir / rel_file
            if not dest.exists():
                self.client.download_file(meta['name'], str(dest), storage_path=meta['id'])


if __name__ == '__main__':
    daemon = GoogleDriveSyncDaemon()
    daemon.pull_cloud_updates()
    print("Daemon sync completed successfully!")
