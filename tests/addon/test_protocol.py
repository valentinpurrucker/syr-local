import re

import pytest

from server.catalog import FULL_GETTERS, UnsafeCommandError
from server.protocol import (
    MAX_BODY_BYTES,
    MAX_COMMANDS,
    MAX_VALUE_LENGTH,
    MessageTooLargeError,
    build_response,
    parse_request_body,
)

from .fixtures import FULL_VALUES, form_body, xml_document


def test_parse_form_encoded_body_with_literal_crlf():
    assert parse_request_body(form_body(FULL_VALUES)) == FULL_VALUES


def test_parse_raw_xml_with_literal_crlf():
    body = xml_document({"getSRN": "204033438", "getCNA": "LEXplus10S"}).encode("iso-8859-2")
    assert parse_request_body(body) == {"getSRN": "204033438", "getCNA": "LEXplus10S"}


def test_parse_escaped_quotes():
    body = (
        '<?xml version=\\"1.0\\"?><sc><d><c n=\\"getMAC\\" v=\\"0c:73:eb:50:ce:c9\\"/>'
        '<c n=\\"getSTA\\" v=\\"\\"/></d></sc>'
    ).encode()
    assert parse_request_body(body) == {"getMAC": "0c:73:eb:50:ce:c9", "getSTA": ""}


@pytest.mark.parametrize("encoding", ["iso-8859-2", "utf-8"])
def test_parse_polish_characters_form_and_raw(encoding):
    status = "Uzupełnij sól, połączono"
    assert parse_request_body(form_body({"getSTA": status}, encoding)) == {"getSTA": status}
    raw = xml_document({"getSTA": status}).encode(encoding)
    assert parse_request_body(raw) == {"getSTA": status}


def test_parse_form_plus_is_space():
    assert parse_request_body(b"xml=%3Cc+n%3D%22getSTA%22+v%3D%22a+b%22+%2F%3E") == {"getSTA": "a b"}


def test_parse_unescapes_html_but_never_expands_custom_entities():
    body = (
        '<!DOCTYPE sc [<!ENTITY boom "x">]><sc><d>'
        '<c n="getSTA" v="a &amp; b &quot;c&quot;" /><c n="getALM" v="&boom;" /></d></sc>'
    ).encode()
    assert parse_request_body(body) == {"getSTA": 'a & b "c"', "getALM": "&boom;"}


def test_parse_drops_non_getters_and_long_values():
    body = (
        '<sc><d><c n="setSIR" v="0" /><c n="getSRN" v="1" />'
        f'<c n="getSTA" v="{"x" * (MAX_VALUE_LENGTH + 1)}" /></d></sc>'
    ).encode()
    assert parse_request_body(body) == {"getSRN": "1"}


def test_parse_literal_newline_inside_value():
    body = b'<sc><d><c n="getSTA" v="line one\\r\\nline two" /></d></sc>'
    assert parse_request_body(body) == {"getSTA": "line one line two"}


def test_parse_empty_body():
    assert parse_request_body(b"") == {}


def test_parse_drops_getters_outside_catalog():
    body = b'<sc><d><c n="getZZZ" v="1" /><c n="getSRN" v="204033438" /></d></sc>'
    assert parse_request_body(body) == {"getSRN": "204033438"}


def test_parse_raw_xml_with_xml_assignment_in_value():
    body = b'<sc><d><c n="getSTA" v="xml=keep this" /></d></sc>'
    assert parse_request_body(body) == {"getSTA": "xml=keep this"}


def test_parse_unknown_getters_cannot_grow_state():
    body = "".join(f'<c n="getZ{i:02d}" v="{i}" />' for i in range(200)).encode()
    assert parse_request_body(body) == {}


def test_parse_limits():
    with pytest.raises(MessageTooLargeError):
        parse_request_body(b"x" * (MAX_BODY_BYTES + 1))
    too_many = "".join(f'<c n="getS{i:02d}" v="" />' for i in range(MAX_COMMANDS + 1))
    with pytest.raises(MessageTooLargeError):
        parse_request_body(too_many.encode())


def test_build_response_only_empty_getters():
    reply = build_response(FULL_GETTERS)
    commands = re.findall(r'<c n="([^"]*)" v="([^"]*)" />', reply)
    assert [name for name, _ in commands] == list(FULL_GETTERS)
    assert all(value == "" for _, value in commands)
    assert reply.count("<c ") == len(FULL_GETTERS)
    assert 'n="set' not in reply.lower()
    assert "getSIR" not in reply


def test_build_empty_response():
    assert build_response(()) == '<?xml version="1.0" encoding="utf-8"?><sc version="1.0"><d></d></sc>'


@pytest.mark.parametrize("bad", [["setSIR"], ["getSIR"], ["getSRN", "setSV1"]])
def test_build_response_refuses_unsafe(bad):
    with pytest.raises(UnsafeCommandError):
        build_response(bad)
