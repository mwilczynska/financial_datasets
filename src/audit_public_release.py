"""Audit the repository for public-release privacy hazards.

This checker deliberately reports findings without printing sensitive values.
Run it from the repository root with:

    python src/audit_public_release.py

Use --no-history to validate only the candidate tree while the current private
history is still present.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_NAME = "mwilczynska"
PUBLIC_EMAIL_SUFFIX = "@users.noreply.github.com"

TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".cmd",
    ".csv",
    ".gitignore",
    ".html",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".ps1",
    ".rst",
    ".sh",
    ".toml",
    ".tsv",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}

ABSOLUTE_WINDOWS_PATH = re.compile(rb"\b[A-Za-z]:[\\/]")
ABSOLUTE_WINDOWS_PATH_TEXT = re.compile(r"\b[A-Za-z]:[\\/]")
ABSOLUTE_POSIX_PATH = re.compile(rb"(?<![A-Za-z0-9])/" + rb"(?:Users|home|private|var/folders)/")
UNC_PATH = re.compile(rb"\\\\[A-Za-z0-9_.-]+[\\/]")
EMAIL_ADDRESS = re.compile(
    rb"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)
PERSONAL_EMAIL = re.compile(
    rb"\b[A-Za-z0-9._%+-]+@(gmail|outlook|hotmail|yahoo|icloud|protonmail)\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)

PRIVATE_KEY = re.compile(
    rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)
CREDENTIAL_URL = re.compile(
    rb"\b[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@",
)
def has_unapproved_email(
    value: bytes,
    *,
    allow_external_source_email: bool = False,
) -> bool:
    """Flag personal-provider emails everywhere and other emails in project text.

    Raw source snapshots can contain third-party contact addresses. Those are
    still subject to source-rights review, but are not treated as the
    maintainer's private identity by this checker.
    """

    if PERSONAL_EMAIL.search(value):
        return True
    if allow_external_source_email:
        return False
    for match in EMAIL_ADDRESS.finditer(value):
        if match.group(0).lower().endswith(PUBLIC_EMAIL_SUFFIX.encode("ascii")):
            continue
        return True
    return False

PRIVATE_PROJECT_REFERENCE = re.compile(
    rb"\b(?:investment|portfolio)[_-](?:tracker|plot)[A-Za-z0-9_*.-]*",
    re.IGNORECASE,
)
SENSITIVE_FILENAME = re.compile(
    r"(^|/)(?:\.env(?:\..*)?|credentials?(?:\..*)?|secrets?(?:\..*)?|"
    r"id_rsa(?:\..*)?|.*\.(?:pem|p12|pfx|key|sqlite|sqlite3|db))$",
    re.IGNORECASE,
)


HISTORY_CONTENT_PATTERNS = {
    "absolute local path": r"(^|[^A-Za-z0-9])[A-Za-z]:[\\/][A-Za-z0-9_.-]+[\\/]|/(Users|home|private|var/folders)/",
    "personal-provider email": r"@(gmail|outlook|hotmail|yahoo|icloud|protonmail)\.[A-Za-z]{2,}",
    "private downstream-project reference": r"investment[ _-]+tracker|portfolio[ _-]+plot",
    "private-key material": r"-----BEGIN [A-Z ]+PRIVATE KEY-----",
    "credential-bearing URL": r"://[^/ @:]+:[^/ @]+@",
}


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def candidate_files() -> list[Path]:
    result = run_git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if result.returncode != 0:
        raise RuntimeError("git ls-files failed")
    return [
        Path(item)
        for item in result.stdout.split("\x00")
        if item
    ]


def iter_text_chunks(path: Path):
    """Yield overlapping byte chunks without loading large files at once."""

    chunk_size = 1024 * 1024
    overlap = b""
    first_chunk = True
    with path.open("rb") as stream:
        while raw := stream.read(chunk_size):
            if first_chunk:
                first_chunk = False
                if b"\x00" in raw[:4096]:
                    return
            combined = overlap + raw
            yield combined
            overlap = combined[-256:]


def scan_tree(files: list[Path]) -> list[str]:
    findings: list[str] = []

    for relative_path in files:
        normalized = relative_path.as_posix()
        if SENSITIVE_FILENAME.search(normalized):
            findings.append(f"candidate sensitive-looking filename: {normalized}")
            continue

        if relative_path.suffix.lower() not in TEXT_SUFFIXES:
            continue

        absolute_path = ROOT / relative_path
        flags = {
            "path": False,
            "email": False,
            "private_key": False,
            "credential_url": False,
            "private_project": False,
        }
        try:
            for file_chunk in iter_text_chunks(absolute_path):
                if b":" in file_chunk or b"/" in file_chunk or b"\\" in file_chunk:
                    flags["path"] |= bool(
                        ABSOLUTE_WINDOWS_PATH.search(file_chunk)
                        or ABSOLUTE_POSIX_PATH.search(file_chunk)
                        or UNC_PATH.search(file_chunk)
                    )
                if b"@" in file_chunk:
                    flags["email"] |= has_unapproved_email(
                        file_chunk,
                        allow_external_source_email=normalized.startswith("sources/raw/"),
                    )
                if b"PRIVATE KEY" in file_chunk:
                    flags["private_key"] |= bool(PRIVATE_KEY.search(file_chunk))
                if b"://" in file_chunk and b"@" in file_chunk:
                    flags["credential_url"] |= bool(CREDENTIAL_URL.search(file_chunk))
                lower_chunk = file_chunk.lower()
                if b"investment" in lower_chunk or b"portfolio" in lower_chunk:
                    flags["private_project"] |= bool(
                        PRIVATE_PROJECT_REFERENCE.search(file_chunk)
                    )
        except OSError:
            findings.append(f"unable to read candidate file: {normalized}")
            continue

        if flags["path"]:
            findings.append(f"absolute local path in: {normalized}")
        if flags["email"]:
            findings.append(f"unapproved email address in: {normalized}")
        if flags["private_key"]:
            findings.append(f"private-key material in: {normalized}")
        if flags["credential_url"]:
            findings.append(f"credential-bearing URL in: {normalized}")
        if flags["private_project"]:
            findings.append(f"private downstream-project reference in: {normalized}")

    for relative_path in files:
        if not relative_path.name.endswith("_build.json"):
            continue

        absolute_path = ROOT / relative_path
        try:
            metadata = json.loads(absolute_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            findings.append(f"unreadable build metadata: {relative_path.as_posix()}")
            continue

        def visit(value: object, key_path: str = "") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, f"{key_path}.{key}" if key_path else key)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{key_path}[{index}]")
            elif isinstance(value, str) and key_path.lower().endswith("_path"):
                if value.startswith("/") or ABSOLUTE_WINDOWS_PATH_TEXT.match(value):
                    findings.append(
                        f"absolute generated path in: {relative_path.as_posix()}"
                    )

        visit(metadata)

    return findings


def history_scope(history_ref: str) -> tuple[str, ...]:
    if history_ref == "--all":
        return ("--all",)
    return (history_ref,)


def scan_history(history_ref: str = "--all") -> list[str]:
    result = run_git("log", *history_scope(history_ref), "--format=%an%x00%ae%x00%cn%x00%ce")
    if result.returncode != 0:
        return ["unable to inspect Git history"]

    bad_records = 0
    for line in result.stdout.splitlines():
        fields = line.split("\x00")
        if len(fields) != 4:
            continue
        author_name, author_email, committer_name, committer_email = fields
        if (
            author_name != PUBLIC_NAME
            or committer_name != PUBLIC_NAME
            or not author_email.lower().endswith(PUBLIC_EMAIL_SUFFIX)
            or not committer_email.lower().endswith(PUBLIC_EMAIL_SUFFIX)
        ):
            bad_records += 1

    if bad_records:
        return [
            f"{bad_records} Git identity records are not using the approved public identity"
        ]
    return []


def scan_history_content(history_ref: str = "--all") -> list[str]:
    """Search reachable history without printing matched content."""

    findings: list[str] = []
    for label, pattern in HISTORY_CONTENT_PATTERNS.items():
        result = run_git(
            "log",
            *history_scope(history_ref),
            "--format=%H",
            "--no-renames",
            "-G",
            pattern,
        )
        if result.returncode != 0:
            findings.append("unable to inspect historical content")
            continue
        commits = {line for line in result.stdout.splitlines() if line}
        if commits:
            findings.append(
                f"{len(commits)} history commits contain {label}"
            )
    return findings


def scan_history_messages(history_ref: str = "--all") -> list[str]:
    """Check reachable commit messages without printing matched content."""

    result = run_git("log", *history_scope(history_ref), "--format=%B")
    if result.returncode != 0:
        return ["unable to inspect Git commit messages"]

    findings: list[str] = []
    for label, pattern in HISTORY_CONTENT_PATTERNS.items():
        if re.search(pattern, result.stdout, flags=re.IGNORECASE):
            findings.append(f"reachable Git commit messages contain {label}")
    return findings


def scan_history_paths(history_ref: str = "--all") -> list[str]:
    """Check reachable historical path names without printing them."""

    result = run_git("rev-list", "--objects", *history_scope(history_ref))
    if result.returncode != 0:
        return ["unable to inspect historical path names"]

    for line in result.stdout.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        path = parts[1]
        if SENSITIVE_FILENAME.search(path):
            return ["reachable Git history contains a sensitive-looking filename"]
        if re.search(
            r"investment[ _-]+tracker|portfolio[ _-]+plot",
            path,
            flags=re.IGNORECASE,
        ):
            return [
                "reachable Git history contains a private downstream-project filename"
            ]
    return []


def scan_remote() -> list[str]:
    result = run_git("remote", "get-url", "origin")
    if result.returncode != 0:
        return []

    parsed = urlsplit(result.stdout.strip())
    if parsed.username or parsed.password:
        return ["origin URL contains embedded credentials"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="skip all reachable Git history checks",
    )
    parser.add_argument(
        "--history-ref",
        default="--all",
        help="Git ref to inspect for history checks (default: all refs)",
    )
    args = parser.parse_args()

    try:
        files = candidate_files()
    except RuntimeError as exc:
        print(f"Public release audit: BLOCKED ({exc})")
        return 1

    findings = scan_tree(files)
    findings.extend(scan_remote())
    if not args.no_history:
        findings.extend(scan_history(args.history_ref))
        findings.extend(scan_history_content(args.history_ref))
        findings.extend(scan_history_messages(args.history_ref))
        findings.extend(scan_history_paths(args.history_ref))

    if findings:
        print("Public release audit: BLOCKED")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Public release audit: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
