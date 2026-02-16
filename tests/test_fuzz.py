"""Fuzz tests for Gatehouse robustness under random input."""

from __future__ import annotations

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from gatehouse.lib import config
from gatehouse.lib.formatter import inject_variables
from gatehouse.lib.models import validate_project_config


class TestConfigGetFuzz:
    """Fuzz the config.get() accessor with arbitrary key paths."""

    @given(st.text(min_size=0, max_size=200))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_get_never_crashes(self, key: str) -> None:
        """config.get() raises KeyError or TypeError for invalid keys, never crashes."""
        try:
            config.get(key)
        except (KeyError, TypeError):
            pass

    @given(st.text(min_size=0, max_size=200))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_get_str_never_crashes(self, key: str) -> None:
        """config.get_str() raises or returns str, never crashes."""
        try:
            result = config.get_str(key)
            assert isinstance(result, str)
        except (KeyError, TypeError):
            pass


class TestInjectVariablesFuzz:
    """Fuzz inject_variables with arbitrary templates and variable maps."""

    @given(
        st.text(min_size=0, max_size=500),
        st.dictionaries(
            keys=st.text(min_size=1, max_size=50),
            values=st.text(min_size=0, max_size=100),
            max_size=10,
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_inject_never_crashes(
        self, template: str, variables: dict[str, str]
    ) -> None:
        """inject_variables never raises on arbitrary inputs."""
        result = inject_variables(template, variables)
        assert isinstance(result, str)


class TestValidateProjectConfigFuzz:
    """Fuzz validate_project_config with arbitrary YAML-like structures."""

    @given(
        st.one_of(
            st.none(),
            st.integers(),
            st.text(),
            st.lists(st.text()),
            st.dictionaries(
                keys=st.text(min_size=0, max_size=20),
                values=st.one_of(
                    st.none(),
                    st.booleans(),
                    st.integers(),
                    st.text(min_size=0, max_size=50),
                    st.lists(st.text(min_size=0, max_size=20)),
                    st.dictionaries(
                        keys=st.text(min_size=0, max_size=10),
                        values=st.text(min_size=0, max_size=20),
                        max_size=5,
                    ),
                ),
                max_size=10,
            ),
        )
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_validate_returns_list_of_strings(self, data: object) -> None:
        """validate_project_config always returns a list of strings."""
        result = validate_project_config(data)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, str)
