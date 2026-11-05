"""Filesystem locations and persisted settings for pdfreader.

Everything the app writes lives under ``%LOCALAPPDATA%\\pdfreader``; the
program never touches the registry.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings

APP_NAME = "pdfreader"
SETTINGS_FILE_NAME = "pdfreader.ini"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return project_root() / relative


def app_executable() -> str:
    return os.path.abspath(sys.executable)


def config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / "AppData" / "Local" / APP_NAME


def settings_file() -> Path:
    return config_dir() / SETTINGS_FILE_NAME


def create_settings() -> QSettings:
    """Settings backed by an INI file instead of the Windows registry."""
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    return QSettings(str(path), QSettings.Format.IniFormat)
