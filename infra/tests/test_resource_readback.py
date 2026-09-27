import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provision import SafeError, assert_subset


def test_azure_location_readback_accepts_display_name_without_weakening_names():
    assert_subset({"location": "koreacentral"}, {"location": "Korea Central"})
    with pytest.raises(SafeError):
        assert_subset({"location": "koreacentral"}, {"location": "East US"})
    with pytest.raises(SafeError):
        assert_subset({"name": "koreacentral"}, {"name": "Korea Central"})
