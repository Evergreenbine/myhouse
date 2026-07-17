"""Back up the configured MySQL database.

The script reads the same ``MYSQL_*`` values used by ``local_db.py`` from
environment variables or ``db_config.local.env``. By default it writes dumps to
``/usr/backdata`` so the server can run it directly from cron or a deploy step.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("db_config.local.env")
DEFAULT_BACKUP_DIR = Path("/usr/backdata")


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _mysql_settings() -> dict[str, str]:
    cfg = _load_env_file(CONFIG_PATH)
    for key in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"):
        if os.environ.get(key) is not None:
            cfg[key] = os.environ[key]
    return {
        "host": cfg.get("MYSQL_HOST", "127.0.0.1"),
        "port": cfg.get("MYSQL_PORT", "3306"),
        "database": cfg.get("MYSQL_DATABASE", "myhouse"),
        "user": cfg.get("MYSQL_USER", "myhouse"),
        "password": cfg.get("MYSQL_PASSWORD", ""),
    }


def backup_mysql(output_dir: Path = DEFAULT_BACKUP_DIR) -> Path:
    settings = _mysql_settings()
    mysqldump = shutil.which("mysqldump")
    if not mysqldump:
        raise RuntimeError("mysqldump not found. Install mysql-client on the server first.")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    database = settings["database"]
    output_file = output_dir / f"{database}_{timestamp}.sql"

    command = [
        mysqldump,
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--no-tablespaces",
        "--default-character-set=utf8mb4",
        f"--host={settings['host']}",
        f"--port={settings['port']}",
        f"--user={settings['user']}",
        f"--result-file={output_file}",
        database,
    ]
    env = os.environ.copy()
    if settings["password"]:
        env["MYSQL_PWD"] = settings["password"]

    subprocess.run(command, env=env, check=True)
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up the configured MySQL database.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help="Directory for .sql backup files. Defaults to /usr/backdata.",
    )
    args = parser.parse_args()
    output_file = backup_mysql(args.output_dir)
    print(f"MySQL backup written to {output_file}")


if __name__ == "__main__":
    main()
