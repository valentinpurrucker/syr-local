"""Parse device requests and build server responses.

The device's XML is not strict XML. It contains literal `\\r\\n` sequences, and
some bodies escape quotes as `\\"`. So bodies are scanned with a tolerant regex
instead of an XML parser, which also means no DTD or entity expansion can
happen. The XML claims utf-8, but the firmware vendor is Polish and the text
has been seen in iso-8859-2, so bytes that are not valid UTF-8 are read as
iso-8859-2.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from urllib.parse import parse_qs

from .catalog import KNOWN_GETTERS, ensure_read_only, is_getter_name

FALLBACK_ENCODING = "iso-8859-2"
MAX_BODY_BYTES = 64 * 1024
MAX_COMMANDS = 512
MAX_VALUE_LENGTH = 512

# <c n="getSRN" v="204033438" />, also with \" instead of ". The value may hold
# backslashes as long as they do not escape the closing quote.
_COMMAND = re.compile(
    r'<c\s+n=\\?"([A-Za-z0-9]{1,16})\\?"\s+v=\\?"((?:[^"\\]|\\(?!"))*)\\?"'
)
_LITERAL_NEWLINE = re.compile(r"(?:\\r|\\n)+")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

_XML_HEADER = '<?xml version="1.0" encoding="utf-8"?>'


class MessageTooLargeError(ValueError):
    """Raised when a request exceeds the body or command limits."""


def parse_request_body(raw: bytes) -> dict[str, str]:
    """Extract `{getter: value}` from a device request body.

    Accepts the raw XML or a form body with an `xml=` field. Names that are not
    getters from the catalog and values that are too long are dropped. Too many
    commands raises.
    """
    if len(raw) > MAX_BODY_BYTES:
        raise MessageTooLargeError(f"body of {len(raw)} bytes exceeds {MAX_BODY_BYTES}")

    # Raw XML starts with `<`; a form body starts with `xml=`. Checking the
    # shape first means an `xml=` sequence inside a status value can never be
    # mistaken for the form field and truncate the body.
    data = raw
    if not raw.lstrip().startswith(b"<"):
        # latin-1 maps every byte to one character, so the form can be split
        # and percent-decoded first and the original bytes recovered afterwards.
        form = parse_qs(raw.decode("latin-1"), keep_blank_values=True, encoding="latin-1")
        if "xml" in form:
            data = form["xml"][0].encode("latin-1")
    text = decode_text(data)

    matches = _COMMAND.findall(text)
    if len(matches) > MAX_COMMANDS:
        raise MessageTooLargeError(f"{len(matches)} commands exceed {MAX_COMMANDS}")

    values: dict[str, str] = {}
    for name, raw_value in matches:
        if not is_getter_name(name) or name not in KNOWN_GETTERS:
            continue
        value = _clean_value(raw_value)
        if len(value) > MAX_VALUE_LENGTH:
            continue
        values[name] = value
    return values


def decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(FALLBACK_ENCODING, errors="replace")


def _clean_value(raw_value: str) -> str:
    value = html.unescape(raw_value)
    value = _LITERAL_NEWLINE.sub(" ", value)
    value = _CONTROL_CHARS.sub("", value)
    return value.strip()


def build_response(names: Iterable[str]) -> str:
    """Render the reply XML. Every name must pass the read-only check, or this raises."""
    commands = "".join(f'<c n="{name}" v="" />' for name in ensure_read_only(names))
    return f'{_XML_HEADER}<sc version="1.0"><d>{commands}</d></sc>'
