"""PyInstaller / development entry point."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from pdfreader.app import main
from pdfreader.i18n import tr


def _log_crash() -> str:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    try:
        base.mkdir(parents=True, exist_ok=True)
        target = base / "pdfreader-crash.log"
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"\n[{datetime.now().isoformat(timespec='seconds')}]\n")
            handle.write(traceback.format_exc())
        return str(target)
    except Exception:
        return ""


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        log_path = _log_crash()
        # A windowed build has no console.  Keep --selftest non-interactive so
        # automated checks cannot hang on a modal dialog.
        if "--selftest" not in sys.argv and getattr(sys, "frozen", False):
            try:
                import ctypes

                message = tr("pdfreader 启动失败。")
                if log_path:
                    message += tr("\n\n详细信息已写入：\n") + log_path
                ctypes.windll.user32.MessageBoxW(None, message, "pdfreader", 0x10)
            except Exception:
                pass
        raise SystemExit(1)
