import re

import pytest

from server.catalog import (
    BASIC_GETTERS,
    FORBIDDEN,
    FULL_GETTERS,
    UnsafeCommandError,
    ensure_read_only,
)
from server.planner import CommandPlanner, Endpoint

GETTER = re.compile(r"^get[A-Z0-9]{2,4}$")


def test_catalog_has_no_duplicates():
    assert len(FULL_GETTERS) == len(set(FULL_GETTERS))
    assert len(BASIC_GETTERS) == len(set(BASIC_GETTERS))


def test_catalog_contains_only_plain_getters():
    for name in FULL_GETTERS:
        assert GETTER.match(name), name
    assert "getSIR" in FORBIDDEN
    assert not set(FULL_GETTERS) & FORBIDDEN
    assert not any(name.lower().startswith("set") for name in FULL_GETTERS)


def test_basic_getters_match_cloud():
    assert BASIC_GETTERS == ("getSRN", "getVER", "getFIR", "getTYP", "getCNA")
    assert set(BASIC_GETTERS) <= set(FULL_GETTERS)


@pytest.mark.parametrize(
    "name",
    ["setSIR", "getSIR", "setSV1", "SETSV1", "getsrn", "get", "getTOOLONG", 'getSRN" v="1', "", None, 1],
)
def test_ensure_read_only_refuses(name):
    with pytest.raises(UnsafeCommandError):
        ensure_read_only(["getSRN", name])


def test_planner_basic_always_identity():
    planner = CommandPlanner(60)
    assert planner.commands_for(Endpoint.BASIC, 0) == BASIC_GETTERS
    assert planner.commands_for(Endpoint.BASIC, 1) == BASIC_GETTERS


def test_planner_full_at_most_once_per_interval():
    planner = CommandPlanner(60)
    assert planner.commands_for(Endpoint.ALL, 100.0) == FULL_GETTERS
    assert planner.commands_for(Endpoint.ALL, 111.0) == ()
    assert planner.commands_for(Endpoint.ALL, 159.9) == ()
    assert planner.commands_for(Endpoint.ALL, 160.0) == FULL_GETTERS
