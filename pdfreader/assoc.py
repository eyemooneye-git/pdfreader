"""Per-user Windows file association for pdfreader.

Everything lives under HKEY_CURRENT_USER, so no administrator rights are
needed and the changes are easy to undo. Windows 10/11 deliberately protects
the final "default app" choice (UserChoice hash), so we register the app as a
candidate and let the user confirm it in Settings.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

import winreg

from .i18n import tr

PROG_ID = "PDFReader.pdf"
APP_KEY = "pdfreader.exe"
APP_NAME = "pdfreader"
CAPABILITIES_KEY = r"Software\PDFReader\Capabilities"
REGISTERED_APPS = r"Software\RegisteredApplications"
CLASSES = r"Software\Classes"

_HKCU = winreg.HKEY_CURRENT_USER
_SHCNE_ASSOCCHANGED = 0x08000000
_SHCNF_IDLIST = 0x0000


class AssocError(Exception):
    pass


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return project_root() / relative


def app_executable() -> str:
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(sys.executable)


def launch_command() -> str:
    """Command Explorer should run for a PDF."""
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}" "%1"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = project_root() / "run_pdfreader.py"
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{runner}" "%1"'


def icon_source() -> str:
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}",0'
    return f'"{resource_path("assets/pdfreader.ico")}",0'


def application_key() -> str:
    return rf"{CLASSES}\Applications\{APP_KEY}"


def _set(key: winreg.HKEYType, name: str, value: str | bytes, kind: int = winreg.REG_SZ) -> None:
    winreg.SetValueEx(key, name, 0, kind, value)


def _create(path: str) -> winreg.HKEYType:
    return winreg.CreateKeyEx(_HKCU, path, 0, winreg.KEY_WRITE)


def _delete_tree(path: str) -> bool:
    """Recursively delete a key (if it exists). Returns True if removed."""
    try:
        key = winreg.OpenKey(_HKCU, path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise AssocError(
            tr("无法打开注册表项 {path}：{error}").format(path=path, error=exc)
        ) from exc

    removed = False
    try:
        while True:
            try:
                child = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_tree(path + "\\" + child)
    finally:
        key.Close()

    try:
        winreg.DeleteKey(_HKCU, path)
        removed = True
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise AssocError(
            tr("无法删除注册表项 {path}：{error}").format(path=path, error=exc)
        ) from exc
    return removed


def _delete_value(path: str, name: str) -> bool:
    try:
        key = winreg.OpenKey(_HKCU, path, 0, winreg.KEY_SET_VALUE)
    except FileNotFoundError:
        return False
    try:
        try:
            winreg.DeleteValue(key, name)
            return True
        except FileNotFoundError:
            return False
    finally:
        key.Close()


def _notify_shell() -> None:
    try:
        ctypes.windll.shell32.SHChangeNotify(
            _SHCNE_ASSOCCHANGED, _SHCNF_IDLIST, None, None
        )
    except Exception:
        pass


def register() -> list[str]:
    """Register pdfreader for the current user. Returns touched key paths."""
    touched: list[str] = []
    command = launch_command()
    icon = icon_source()
    exe_name = os.path.basename(app_executable())

    try:
        # ProgID -------------------------------------------------------------
        prog = rf"{CLASSES}\{PROG_ID}"
        with _create(prog) as key:
            _set(key, "", tr("PDF 文档"))
            _set(key, "FriendlyTypeName", tr("PDF 文档"))
        with _create(prog + r"\DefaultIcon") as key:
            _set(key, "", icon)
        with _create(prog + r"\shell\open\command") as key:
            _set(key, "", command)
        with _create(prog + r"\Application") as key:
            _set(key, "ApplicationName", APP_NAME)
            _set(key, "ApplicationDescription", tr("轻量 PDF 阅读器"))
            _set(key, "ApplicationIcon", icon)
        touched.append(prog)

        # "Open with" --------------------------------------------------------
        with _create(rf"{CLASSES}\.pdf\OpenWithProgids") as key:
            _set(key, PROG_ID, b"", winreg.REG_NONE)
        touched.append(rf"{CLASSES}\.pdf\OpenWithProgids")
        with _create(rf"{CLASSES}\.pdf\OpenWithList") as key:
            _set(key, APP_KEY, "")
        touched.append(rf"{CLASSES}\.pdf\OpenWithList")

        # Applications\<exe> ------------------------------------------------
        app_key = application_key()
        with _create(app_key) as key:
            _set(key, "FriendlyAppName", APP_NAME)
            _set(key, "ApplicationCompany", "pdfreader")
        with _create(app_key + r"\DefaultIcon") as key:
            _set(key, "", icon)
        with _create(app_key + r"\shell\open\command") as key:
            _set(key, "", command)
        with _create(app_key + r"\SupportedTypes") as key:
            _set(key, ".pdf", "")
        touched.append(app_key)

        # Default-apps capabilities ---------------------------------------
        with _create(CAPABILITIES_KEY) as key:
            _set(key, "ApplicationName", APP_NAME)
            _set(
                key,
                "ApplicationDescription",
                tr("轻量、离线、可复制文字的 PDF 阅读器"),
            )
            _set(key, "ApplicationIcon", icon)
        with _create(CAPABILITIES_KEY + r"\FileAssociations") as key:
            _set(key, ".pdf", PROG_ID)
        with winreg.CreateKeyEx(_HKCU, REGISTERED_APPS, 0, winreg.KEY_SET_VALUE) as key:
            _set(key, APP_NAME, CAPABILITIES_KEY)
        touched.append(CAPABILITIES_KEY)
        touched.append(REGISTERED_APPS)
    except OSError as exc:
        raise AssocError(tr("写入注册表失败：{error}").format(error=exc)) from exc

    _notify_shell()
    return touched


def unregister() -> list[str]:
    """Remove every registry entry this app added. Returns removed paths."""
    removed: list[str] = []
    candidates = [
        rf"{CLASSES}\{PROG_ID}",
        application_key(),
        r"Software\PDFReader",
    ]
    for path in candidates:
        if _delete_tree(path):
            removed.append(path)

    if _delete_value(rf"{CLASSES}\.pdf\OpenWithProgids", PROG_ID):
        removed.append(rf"{CLASSES}\.pdf\OpenWithProgids\{PROG_ID}")
    if _delete_value(rf"{CLASSES}\.pdf\OpenWithList", APP_KEY):
        removed.append(rf"{CLASSES}\.pdf\OpenWithList\{APP_KEY}")
    if _delete_value(REGISTERED_APPS, APP_NAME):
        removed.append(rf"{REGISTERED_APPS}\{APP_NAME}")

    _notify_shell()
    return removed


def current_command() -> str | None:
    try:
        with winreg.OpenKey(_HKCU, rf"{CLASSES}\{PROG_ID}\shell\open\command") as key:
            return str(winreg.QueryValueEx(key, "")[0])
    except OSError:
        return None


def registration_status() -> tuple[bool, str]:
    """(registered_for_this_exe, human readable detail)."""
    command = current_command()
    if not command:
        return False, tr("尚未注册文件关联")
    expected = launch_command()
    if command.strip().lower() == expected.strip().lower():
        return True, tr("已注册（当前 exe）")
    return False, tr("已注册到另一个位置：{command}").format(command=command)


def default_apps_hint() -> str:
    return tr(
        "Windows 11 不允许程序静默修改默认应用。注册后请到"
        "“设置 → 应用 → 默认应用 → pdfreader → .pdf”确认即可。"
    )
