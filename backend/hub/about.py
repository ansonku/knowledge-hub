"""P24: what the setup wizard and the About page say about this software. Empty links are shown as "即將開放"."""
from pathlib import Path

VERSION = "1.0.0"
DEVELOPER = {
    "name": "ansonku",
    "email": "ansonku@gmail.com",
    "github": "https://github.com/ansonku/knowledge-hub",
}
COPYRIGHT = "2026 ansonku"
LICENSE = ""  # not chosen yet: shown as 「待定」
SUPPORT = {
    "github_sponsors": "",  # to be filled once applied for
    "buy_me_a_coffee": "",
}
TERMS_VERSION = 1
TERMS_FILE = Path(__file__).with_name("terms.md")


def terms():
    """The terms as [{"title", "body"}], from `## ` headings in terms.md."""
    sections, current = [], None
    for line in TERMS_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = {"title": line[3:].strip(), "body": []}
            sections.append(current)
        elif current is not None and line.strip():
            current["body"].append(line.strip())
    return [{"title": section["title"], "body": "\n".join(section["body"])} for section in sections]


def public():
    return {
        "version": VERSION, "developer": DEVELOPER, "copyright": COPYRIGHT, "license": LICENSE,
        "support": SUPPORT, "terms_version": TERMS_VERSION, "terms": terms(),
    }
