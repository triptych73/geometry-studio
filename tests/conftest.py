"""Shared fixtures for the Parametric Staircase Studio test suite."""
import sys
import os
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from staircase_parametric import DEFAULT_CONFIG as PARAM_DEFAULTS
from staircase_structural import DEFAULT_CONFIG as STRUCT_DEFAULTS


@pytest.fixture
def default_parametric_config():
    """Returns a copy of the default parametric configuration."""
    return PARAM_DEFAULTS.copy()


@pytest.fixture
def default_structural_config():
    """Returns a copy of the default structural configuration."""
    config = PARAM_DEFAULTS.copy()
    config.update(STRUCT_DEFAULTS)
    return config


@pytest.fixture
def minimal_config():
    """Minimal config for fast tests — small staircase."""
    config = PARAM_DEFAULTS.copy()
    config.update(STRUCT_DEFAULTS)
    config.update({
        "s_bottom_steps": 2,
        "winder_steps": 2,
        "s_top_steps": 2,
        "width": 600,
        "unified_soffit": False,
    })
    return config
