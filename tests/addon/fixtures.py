"""Device request bodies modelled on the captured traffic (values from the handoff)."""

from __future__ import annotations

from urllib.parse import quote

XML_HEADER = '<?xml version="1.0" encoding="utf-8"?>'

FULL_VALUES = {
    "getSRN": "204033438",
    "getVER": "2.0",
    "getFIR": "SLPS",
    "getTYP": "80",
    "getCNA": "LEXplus10S",
    "getMAN": "Syr",
    "getMAC": "0C:73:EB:50:CE:C9",
    "getIPA": "192.168.178.130",
    "getDGW": "192.168.178.1",
    "getALM": "",
    "getSTA": "",
    "getCS1": "60",
    "getFLO": "0",
    "getRES": "1215",
    "getCOF": "583939",
    "getRG1": "0",
    "getPRS": "48",
    "getLAR": "1767325517",
    "getTOR": "391",
    "getSS1": "5",
    "getSV1": "8",
}


def xml_document(values: dict[str, str], newline: str = "\\r\\n") -> str:
    """Render values like the device does: literal backslash-r-backslash-n between lines."""
    commands = newline.join(f'<c n="{name}" v="{value}" />' for name, value in values.items())
    return f'{XML_HEADER}{newline}<sc version="1.0">{newline}<d>{newline}{commands}{newline}</d></sc>'


def form_body(values: dict[str, str], encoding: str = "iso-8859-2") -> bytes:
    """GetAllCommands body: form field xml=, percent-encoded (iso-8859-2 by default)."""
    return ("xml=" + quote(xml_document(values), safe="", encoding=encoding)).encode("ascii")
