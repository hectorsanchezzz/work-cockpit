"""Things that differ between macOS and Windows, in one place.

- PY: the Python that runs the other scripts (the one running this one).
- LOCK: the refresh lock, a directory in the system temp folder (works on both systems).
- child_env(): environment for child scripts: UTF-8 on (Windows defaults to cp1252) and ~/bin on PATH.
- secret(): API keys. Order: environment variable, then the `keyring` package (Windows Credential
  Manager / macOS Keychain) if installed. Never written to disk, printed or logged.
- EKCTL: the macOS Reminders/Calendar helper. None when it is not there (always on Windows).
"""
import os
import sys
import tempfile

PY = sys.executable
LOCK = os.path.join(tempfile.gettempdir(), "cockpit-refresh.lock")
IS_WINDOWS = os.name == "nt"


def child_env():
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if IS_WINDOWS:  # programs installed after this process started (gh, python): reload PATH from the registry
        import winreg
        parts = []
        for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, "Environment")):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
            except OSError:
                pass
        env["PATH"] = os.pathsep.join(parts + [env.get("PATH", "")])
    extra = os.path.expanduser("~/bin")
    if os.path.isdir(extra):
        env["PATH"] = env.get("PATH", "") + os.pathsep + extra
    return env


def _find_ekctl():
    p = os.path.expanduser("~/bin/ekctl")
    return p if (not IS_WINDOWS and os.path.exists(p)) else None


EKCTL = _find_ekctl()


def secret(service, env_var):
    """Return the key or raise RuntimeError saying where to put it (never the key itself)."""
    val = os.environ.get(env_var, "").strip()
    if val:
        return val
    try:
        import keyring
        val = (keyring.get_password(service, "cockpit") or "").strip()
        if val:
            return val
    except Exception:  # keyring missing or no backend: fall through to the message below
        pass
    raise RuntimeError(
        f"no key found. Set the {env_var} environment variable, or run: "
        f"python -m keyring set {service} cockpit")
