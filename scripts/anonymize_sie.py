"""Anonymize SIE4 files by replacing sensitive company and personal data.

Replaces company names, org numbers, addresses, person names in
cost centers, and free text in vouchers/transactions — while keeping
account numbers, amounts, dates, and dimensions intact so the file
remains valid for parser testing.

Usage:
    python scripts/anonymize_sie.py input.se output.se
    python scripts/anonymize_sie.py input.se  # prints to stdout
"""

import re
import sys
import hashlib
from pathlib import Path


# --- Configuration: what to replace ---

COMPANY_NAME = "Demoföretaget AB"
ORG_NR = "556000-0000"
CONTACT_PERSON = "Test Testsson"
STREET = "Exempelgatan 1"
POSTAL = "100 00 Stockholm"
PHONE = "070-000 00 00"
FNR = "000001"

# Known sensitive words to scrub from free text everywhere.
# Add more if you spot leaks after a first run.
SENSITIVE_WORDS = [
    # Company / brand
    "Ljusgårda", "Ljusgarda", "Solgården", "Solgarden",
    "PLANESTATE INVEST", "PHILIAN", "Klaravik",
    "DAGAB", "Hemköp", "Hemkop", "ICA", "COOP",
    "Närkefrakt", "Narkefrakt", "Skaraborgs Kyltransporter",
    "Tower Farm", "ARALAB", "Phenospex", "IIVO",
    "Pleo", "PleoInvoice", "PLEO",
    "Webport", "PRIVA", "Mind Energy", "Tibro Energi",
    # Person names found in #OBJEKT, #VER, #BTRANS, #RTRANS
    "Anna Patricia Aganovic", "Martina Engvall", "Joel Wehage",
    "Markus Alvila", "Anna-Karin",
    "Hélène", "Helene", "Hålene",
    # Location
    "Tibro", "Järnvägsgatan", "Jarnvagsgatan",
]

# Short person names — only replaced as whole words to avoid
# false positives (e.g. "Erik" in "Amerika" or "Mats" in "Automats").
SENSITIVE_WHOLE_WORDS = [
    "Mats", "Niklas", "Andreas", "Erik", "Marcus", "Ulf",
    "Jesper", "Eric", "Jonas", "Kristian",
]

# Generic names for person-named cost centers
PERSON_CC_MAP = {}
_person_counter = 0


def _generic_person(name: str) -> str:
    """Return a consistent generic replacement for a person name."""
    global _person_counter
    if name not in PERSON_CC_MAP:
        _person_counter += 1
        PERSON_CC_MAP[name] = f"Person {_person_counter}"
    return PERSON_CC_MAP[name]


def _stable_hash(text: str, prefix: str = "Ref") -> str:
    """Deterministic short hash so same input → same anonymized output."""
    h = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()[:6]
    return f"{prefix}-{h}"


def _scrub_sensitive(text: str) -> str:
    """Replace known sensitive words in a string."""
    result = text
    for word in sorted(SENSITIVE_WORDS, key=len, reverse=True):
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        result = pattern.sub("XXX", result)
    # Whole-word matches for short names (avoids "Erik" matching "Amerika")
    for word in SENSITIVE_WHOLE_WORDS:
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        result = pattern.sub("XXX", result)
    return result


def anonymize_header(line: str) -> str:
    """Anonymize SIE header fields."""
    if line.startswith("#FNAMN "):
        return f'#FNAMN "{COMPANY_NAME}"'
    if line.startswith("#ORGNR "):
        return f"#ORGNR {ORG_NR}"
    if line.startswith("#FNR "):
        return f"#FNR {FNR}"
    if line.startswith("#ADRESS "):
        return f'#ADRESS "{CONTACT_PERSON}" "{STREET}" "{POSTAL}" "{PHONE}" '
    return line


def anonymize_objekt(line: str) -> str:
    """Anonymize #OBJEKT lines — replace names but keep codes."""
    # Format: #OBJEKT dim "code" "name"
    m = re.match(r'(#OBJEKT\s+\d+\s+"[^"]*")\s+"([^"]*)"', line)
    if not m:
        return line
    prefix = m.group(1)
    name = m.group(2)
    clean_name = _scrub_sensitive(name)
    return f'{prefix} "{clean_name}"'


def anonymize_ver(line: str) -> str:
    """Anonymize #VER lines — replace description text."""
    # Format: #VER series number date "text" regdate [sign]
    m = re.match(r'(#VER\s+\S+\s+\d+\s+\d+)\s+"([^"]*)"(.*)', line)
    if not m:
        return line
    prefix = m.group(1)
    text = m.group(2)
    suffix = m.group(3)
    if text.strip():
        anon_text = _stable_hash(text, "Ver")
    else:
        anon_text = ""
    return f'{prefix} "{anon_text}"{suffix}'


def anonymize_trans(line: str) -> str:
    """Anonymize #TRANS / #BTRANS / #RTRANS lines.

    Replaces ALL quoted strings that contain text (free-text descriptions
    and user signatures) while preserving empty strings and dimension refs.
    """
    # Format: #TRANS account {dims} amount "date" "text" quantity ["sign"]
    # #BTRANS and #RTRANS have same format + trailing "username" field
    parts = list(re.finditer(r'"([^"]*)"', line))
    if not parts:
        return line

    result = line
    # Process matches in reverse order so indices stay valid
    for match in reversed(parts):
        text = match.group(1)
        # Skip empty strings and dimension references (inside {})
        if not text.strip():
            continue
        # Check if this quoted string is inside curly braces (dimension ref)
        before = result[:match.start()]
        open_braces = before.count("{") - before.count("}")
        if open_braces > 0:
            continue
        # Replace with hash for text, "Användare" for trailing signature
        anon = _stable_hash(text, "Tx")
        result = result[:match.start(1)] + anon + result[match.end(1):]

    return result


def anonymize_konto(line: str) -> str:
    """Anonymize #KONTO lines — scrub company-specific account names."""
    m = re.match(r'(#KONTO\s+\d+)\s+"([^"]*)"', line)
    if not m:
        return line
    prefix = m.group(1)
    name = m.group(2)
    clean_name = _scrub_sensitive(name)
    return f'{prefix} "{clean_name}"'


def anonymize_line(line: str) -> str:
    """Route a single SIE line to the appropriate anonymizer."""
    if line.startswith("#FNAMN ") or line.startswith("#ORGNR ") or \
       line.startswith("#FNR ") or line.startswith("#ADRESS "):
        return anonymize_header(line)
    if line.startswith("#OBJEKT "):
        return anonymize_objekt(line)
    if line.startswith("#VER "):
        return anonymize_ver(line)
    if line.startswith(("#TRANS ", "#BTRANS ", "#RTRANS ")):
        return anonymize_trans(line)
    if line.startswith("#KONTO "):
        return anonymize_konto(line)
    return line


def anonymize_file(input_path: str, output_path: str | None = None) -> None:
    """Read a SIE file, anonymize it, and write the result."""
    # SIE files use CP437 (PC8) encoding
    with open(input_path, "r", encoding="cp437") as f:
        lines = f.readlines()

    result = []
    for line in lines:
        stripped = line.rstrip("\n").rstrip("\r")
        anon = anonymize_line(stripped)
        result.append(anon)

    output = "\n".join(result) + "\n"

    if output_path:
        # Write as CP437 to keep SIE-compatible
        with open(output_path, "w", encoding="cp437") as f:
            f.write(output)
        print(f"✅ Anonymized: {input_path} → {output_path}")
    else:
        sys.stdout.write(output)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not Path(input_path).exists():
        print(f"❌ File not found: {input_path}")
        sys.exit(1)

    anonymize_file(input_path, output_path)


if __name__ == "__main__":
    main()
