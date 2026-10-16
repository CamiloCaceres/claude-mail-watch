"""mail-watch standalone watcher: report inbox mail that arrived since the last run.

Python 3.9+ standard library only. The mod pipes this file to `python3 -` and reads one
line of JSON back:

    {"account", "initialized", "new": [...], "state": {...}}            on success
    {"account", "error": "..."}                                          on failure

Each entry in "new" has id (IMAP sequence number), uid, from, address, subject, date,
trust and auth. trust is one of:

    trusted   the address is on the trusted list AND the receiving server says the
              message authenticated (DMARC pass, or aligned DKIM or SPF pass)
    spoofed   the address is on the trusted list but the message did NOT authenticate
    external  anyone else

Only trusted mail carries "body": its plain text, cut to --max-body characters.
Headers are fetched with BODY.PEEK, so nothing is marked as read. The password is read
from the environment variable --password-env, or from that key in --dotenv; it is never
printed.
"""

from __future__ import annotations

import argparse
import email
import email.policy
import imaplib
import json
import os
import re
import sys
from email.header import decode_header, make_header
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional


def read_dotenv(path: str, name: str) -> Optional[str]:
    """One value from a KEY=VALUE file; None when the file or the key is missing."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep or key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        return value
    return None


def password_from(env_name: str, dotenv: Optional[str]) -> Optional[str]:
    value = os.environ.get(env_name)
    if value:
        return value
    return read_dotenv(dotenv, env_name) if dotenv else None


def decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def domain_of(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower() if "@" in address else ""


def aligned(domain: str, from_domain: str) -> bool:
    """Relaxed DMARC alignment: same organizational domain, roughly (one is a subdomain of the other)."""
    if not domain or not from_domain:
        return False
    domain, from_domain = domain.lower().strip("."), from_domain.lower().strip(".")
    return domain == from_domain or domain.endswith("." + from_domain) or from_domain.endswith("." + domain)


def authenticated(msg: email.message.Message, from_domain: str) -> Dict[str, Any]:
    """Read the topmost Authentication-Results header: the one the receiving server added last.

    Lower ones can be written by anyone who sends mail, so they are ignored.
    """
    header = msg.get_all("Authentication-Results") or []
    if not header:
        return {"pass": False, "reason": "no Authentication-Results header"}
    results = " ".join(str(header[0]).split()).lower()

    def method(name: str) -> List[Dict[str, str]]:
        found = []
        for match in re.finditer(rf"\b{name}=(\w+)([^;]*)", results):
            props = dict(re.findall(r"([\w.]+)=([^\s;]+)", match.group(2)))
            found.append({"result": match.group(1), **props})
        return found

    if any(m["result"] == "pass" for m in method("dmarc")):
        return {"pass": True, "reason": "dmarc=pass"}
    for m in method("dkim"):
        signer = m.get("header.d") or domain_of(m.get("header.i", ""))
        if m["result"] == "pass" and aligned(signer, from_domain):
            return {"pass": True, "reason": f"dkim=pass ({signer})"}
    for m in method("spf"):
        mailfrom = domain_of(m.get("smtp.mailfrom", "")) or m.get("smtp.mailfrom", "")
        if m["result"] == "pass" and aligned(mailfrom, from_domain):
            return {"pass": True, "reason": f"spf=pass ({mailfrom})"}
    return {"pass": False, "reason": "no aligned dmarc, dkim or spf pass"}


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def body_text(msg: email.message.Message, limit: int) -> str:
    plain, html = None, None
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        kind = part.get_content_type()
        if kind not in ("text/plain", "text/html"):
            continue
        try:
            text = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            text = payload.decode(part.get_content_charset() or "utf-8", "replace")
        if kind == "text/plain" and plain is None:
            plain = text
        elif kind == "text/html" and html is None:
            html = text
    if plain is None and html is not None:
        parser = _TextOnly()
        parser.feed(html)
        plain = "".join(parser.parts)
    text = re.sub(r"\n{3,}", "\n\n", (plain or "").replace("\r\n", "\n")).strip()
    return text if len(text) <= limit else text[:limit] + "\n[... cut]"


def classify(msg: email.message.Message, trusted: List[str]) -> Dict[str, Any]:
    sender = decode(msg.get("From", ""))
    address = parseaddr(sender)[1].lower()
    auth = authenticated(msg, domain_of(address))
    if address and address in trusted:
        trust = "trusted" if auth["pass"] else "spoofed"
    else:
        trust = "external"
    return {"from": sender, "address": address, "trust": trust, "auth": auth["reason"]}


def watch(args: argparse.Namespace) -> Dict[str, Any]:
    password = password_from(args.password_env, args.dotenv)
    if not password:
        return {"account": args.user, "error": f"no password: set {args.password_env} in the environment or in .env"}
    trusted = [a.strip().lower() for a in args.trusted.split(",") if a.strip()]
    state = json.loads(args.state) if args.state else {}

    mail = imaplib.IMAP4_SSL(args.host, args.port)
    try:
        mail.login(args.user, password)
        mail.select("INBOX", readonly=True)
        typ, data = mail.uid("SEARCH", None, "ALL")
        uids = sorted(int(u) for u in (data[0].split() if typ == "OK" and data and data[0] else []))
        typ, vdata = mail.status("INBOX", "(UIDVALIDITY)")
        found = re.search(rb"UIDVALIDITY (\d+)", vdata[0] if typ == "OK" and vdata else b"")
        validity = int(found.group(1)) if found else None

        last = state.get("last_uid")
        result: Dict[str, Any] = {"account": args.user, "initialized": False, "new": []}
        if last is None or state.get("uidvalidity") != validity:
            result["initialized"] = True
            last = max(uids, default=0)
        else:
            for uid in (u for u in uids if u > last):
                typ, msg_data = mail.uid("FETCH", str(uid), "(BODY.PEEK[HEADER])")
                if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                    continue
                seq = msg_data[0][0].split(b" ", 1)[0].decode()
                headers = email.message_from_bytes(msg_data[0][1], policy=email.policy.default)
                entry = {"id": seq, "uid": uid, **classify(headers, trusted),
                         "subject": decode(headers.get("Subject", "(no subject)")),
                         "date": str(headers.get("Date", ""))}
                if entry["trust"] == "trusted" and args.max_body > 0:
                    typ, full = mail.uid("FETCH", str(uid), "(BODY.PEEK[])")
                    if typ == "OK" and full and isinstance(full[0], tuple):
                        whole = email.message_from_bytes(full[0][1], policy=email.policy.default)
                        entry["body"] = body_text(whole, args.max_body)
                result["new"].append(entry)
            last = max(uids, default=last)
        result["state"] = {"last_uid": last, "uidvalidity": validity}
        return result
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Report inbox mail that arrived since the last run, as JSON.")
    parser.add_argument("--host", required=True, help="IMAP server, e.g. imap.purelymail.com")
    parser.add_argument("--port", type=int, default=993, help="IMAP port (SSL)")
    parser.add_argument("--user", required=True, help="Mailbox address, also the IMAP login")
    parser.add_argument("--password-env", default="MAIL_WATCH_PASSWORD", help="Variable that holds the password")
    parser.add_argument("--dotenv", help="KEY=VALUE file to read the password from when the variable is unset")
    parser.add_argument("--trusted", default="", help="Comma-separated sender addresses that may wake the agent")
    parser.add_argument("--state", default="", help="The state JSON the previous run printed")
    parser.add_argument("--max-body", type=int, default=4000, help="Characters of a trusted mail's body to include")
    args = parser.parse_args(argv)
    try:
        result = watch(args)
    except (imaplib.IMAP4.error, OSError, ValueError) as err:
        result = {"account": args.user, "error": f"{type(err).__name__}: {err}"}
    print(json.dumps(result))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
