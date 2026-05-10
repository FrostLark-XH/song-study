#!/usr/bin/env python3
"""Send files to Feishu chat via Open API. Handles UTF-8 filenames correctly.

Credentials are read from ~/.cc-connect/config.toml — NEVER hardcoded.
"""
import sys, json, os, tomllib
from pathlib import Path
from urllib.request import Request, urlopen

CONFIG_PATH = Path.home() / ".cc-connect" / "config.toml"
SESSION_DIR = Path.home() / ".cc-connect" / "sessions"
BOUNDARY = "----FormBoundary7MA4YWxkTrZu0gW"


def _read_config():
    """Extract feishu app_id/app_secret from cc-connect config.toml."""
    data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    for proj in data.get("projects", []):
        for plat in proj.get("platforms", []):
            if plat.get("type") == "feishu":
                opts = plat.get("options", {})
                return opts["app_id"], opts["app_secret"]
    raise RuntimeError("No feishu platform config found in config.toml")


def _find_chat_id():
    """Find the active feishu chat_id from session files."""
    for f in sorted(SESSION_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            active = data.get("active_session", {})
            for key in active:
                if key.startswith("feishu:oc_"):
                    return key.split(":")[1]
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
    raise RuntimeError("No active feishu session found")


def get_token(app_id, app_secret):
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=data, headers={"Content-Type": "application/json"},
    )
    return json.loads(urlopen(req).read())["tenant_access_token"]


def upload_file(token, filepath):
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        file_bytes = f.read()

    header = (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file_type"\r\n'
        f"\r\n"
        f"stream\r\n"
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file_name"\r\n'
        f"\r\n"
        f"{filename}\r\n"
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n"
        f"\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{BOUNDARY}--\r\n".encode()
    body = header + file_bytes + footer

    req = Request(
        "https://open.feishu.cn/open-apis/im/v1/files",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={BOUNDARY}",
        },
    )
    resp = json.loads(urlopen(req).read())
    code = resp.get("code", -1)
    fk = resp.get("data", {}).get("file_key", "N/A")
    print(f"[UPLOAD] {filename} -> code={code} file_key={fk}")
    if code != 0:
        print(f"  ERROR: {resp.get('msg', 'unknown')}")
    return fk


def send_file_msg(token, chat_id, file_key):
    inner = json.dumps({"file_key": file_key})
    data = json.dumps({
        "receive_id": chat_id,
        "msg_type": "file",
        "content": inner,
    }).encode()

    req = Request(
        f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    resp = json.loads(urlopen(req).read())
    code = resp.get("code", -1)
    mid = resp.get("data", {}).get("message_id", "N/A")
    print(f"[SEND] file_key={file_key} -> code={code} message_id={mid}")
    if code != 0:
        print(f"  ERROR: {resp.get('msg', 'unknown')}")
    return resp


if __name__ == "__main__":
    files = sys.argv[1:]
    if not files:
        print("Usage: PYTHONUTF8=1 python feishu_sender.py <file1> [file2 ...]")
        sys.exit(1)

    app_id, app_secret = _read_config()
    chat_id = _find_chat_id()
    token = get_token(app_id, app_secret)
    print(f"[AUTH] token={token[:20]}... chat_id={chat_id}")

    for fp in files:
        fk = upload_file(token, fp)
        send_file_msg(token, chat_id, fk)

    print("[DONE] All files sent.")
