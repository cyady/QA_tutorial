from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path
from typing import IO

from dotenv import load_dotenv
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slackbot_for_web.config import load_settings
from slackbot_for_web.slack_app import build_slack_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    project_root = Path(__file__).resolve().parents[2]
    lock_handle = _acquire_single_instance_lock(project_root)
    dotenv_path = project_root / ".env"
    load_dotenv(dotenv_path=dotenv_path)
    _configure_ssl_certificates()
    settings = load_settings()
    logging.getLogger(__name__).info("Loaded .env from %s", dotenv_path)
    logging.getLogger(__name__).info("Artifact root: %s", settings.artifact_root)
    app = build_slack_app(settings)
    handler = SocketModeHandler(app, settings.slack_app_token)
    # Keep the lock file handle alive for the process lifetime.
    _ = lock_handle
    handler.start()


def _acquire_single_instance_lock(project_root: Path) -> IO[str]:
    lock_path = project_root / ".bot.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt  # pylint: disable=import-outside-toplevel

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # pylint: disable=import-outside-toplevel

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError(
            "Another slackbot_for_web instance is already running. "
            "Stop the existing process first."
        ) from exc

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()

    def _release() -> None:
        try:
            if os.name == "nt":
                import msvcrt  # pylint: disable=import-outside-toplevel

                handle.seek(0)
                handle.truncate()
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl  # pylint: disable=import-outside-toplevel

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        finally:
            try:
                handle.close()
            except Exception:
                pass

    atexit.register(_release)
    return handle


def _configure_ssl_certificates() -> None:
    if os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE"):
        return
    try:
        import certifi  # pylint: disable=import-outside-toplevel
    except Exception:
        return
    ca_bundle = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)


if __name__ == "__main__":
    main()
