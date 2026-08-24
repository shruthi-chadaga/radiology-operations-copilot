"""End-to-end exercised flow against the running Docker stack.

Cookie-based auth, synthetic-only data. Prints one line per step:
PASS/FAIL <step> <detail>
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000/api/v1"
ENV_PATH = r"C:\Users\abhin\radiology-operations-copilot\.env"
RESULTS: list[tuple[bool, str, str]] = []


def load_env() -> dict[str, str]:
    creds = {}
    with open(ENV_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                creds[key.strip()] = value
    return creds


class Client:
    """Cookie-jar HTTP client for one authenticated user."""

    def __init__(self, label: str, email: str, password: str) -> None:
        self.label = label
        self.cookie = ""
        self.email = email
        self._login(email, password)

    def _login(self, email: str, password: str) -> None:
        req = urllib.request.Request(
            f"{BASE}/auth/login",
            data=json.dumps({"email": email, "password": password}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                set_cookie = resp.headers.get("Set-Cookie", "")
                resp.read()
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"login failed for {email}: {exc.code}") from exc
        match = re.search(r"access_token=([^;]+)", set_cookie)
        if not match:
            raise SystemExit(f"no access_token cookie for {email}")
        self.cookie = match.group(1)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        raw_body: bytes | None = None,
        expect: int | tuple[int, ...] = 200,
    ) -> tuple[int, object, bytes, dict]:
        headers = {"Cookie": f"access_token={self.cookie}"}
        if self.email:
            headers["Origin"] = "http://localhost:3000"
        data = None
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(json_body).encode()
        elif raw_body is not None:
            data = raw_body
        req = urllib.request.Request(
            BASE + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                payload = resp.read()
                content_type = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            status = exc.code
            payload = exc.read()
            content_type = exc.headers.get("Content-Type", "")
        ok = status in (expect if isinstance(expect, tuple) else (expect,))
        parsed: object
        try:
            parsed = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            parsed = {"_raw_bytes": len(payload)}
        RESULTS.append((ok, f"{method} {path} as {self.label}", f"got {status}, expected {expect}"))
        return status, parsed, payload, {"content-type": content_type}


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((condition, name, detail))


def main() -> int:
    env = load_env()
    admin = Client("pacs_admin", "pacsadmin@example.local", env["PACS_ADMIN_DEMO_PASSWORD"])
    manager = Client("manager", "manager@example.local", env["OPERATIONS_MANAGER_DEMO_PASSWORD"])
    auditor = Client("auditor", "auditor@example.local", env["AUDITOR_DEMO_PASSWORD"])

    # ---- Session / auth surface -------------------------------------------------
    me = admin.request("GET", "/auth/me")
    check("auth.me returns pacs_admin role", me[1].get("role") == "pacs_admin", str(me[1]))

    # ---- Worklist + studies present --------------------------------------------
    wl = admin.request("GET", "/imaging/worklist")
    items = wl[1].get("items", []) if isinstance(wl[1], dict) else []
    check("imaging worklist responds", isinstance(wl[1], dict), f"{len(items)} items")

    sync = admin.request("POST", "/pacs/studies/sync", expect=(200, 201))
    synced = sync[1] if isinstance(sync[1], dict) else {}
    check(
        "PACS inventory sync observes seeded studies",
        bool(synced) and (synced.get("observed") or synced.get("created") or synced.get("updated")),
        str({k: v for k, v in synced.items() if not isinstance(v, list)})[:160],
    )

    studies_page = admin.request("GET", "/pacs/studies")
    page = studies_page[1] if isinstance(studies_page[1], dict) else {}
    studies = page.get("items", [])
    check("PACS inventory lists seeded studies", len(studies) == 5, f"{len(studies)} studies")
    if not studies:
        return report()
    study = studies[0]
    study_id = study["id"]

    qido = admin.request("GET", "/imaging/dicom/studies")
    qrows = qido[1] if isinstance(qido[1], list) else []
    check(
        "QIDO-style query returns the same inventory",
        len(qrows) >= 5,
        f"{len(qrows)} rows",
    )
    first = qrows[0] if qrows else {}
    check(
        "QIDO row carries DICOM tags",
        all(tag in first for tag in ("0020000D", "00080050", "00100020")),
        "",
    )

    mwl = admin.request("GET", "/imaging/modality-worklist?window_hours=168")
    mw_rows = mwl[1].get("items", []) if isinstance(mwl[1], dict) else []
    check("MWL endpoint responds with items list", isinstance(mwl[1], dict), f"{len(mw_rows)} scheduled entries (0 valid if nothing booked)")

    return report()


def report() -> int:
    passed = sum(1 for ok, _, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n===== E2E PROGRESS: {passed}/{total} checks passed =====")
    for ok, name, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
