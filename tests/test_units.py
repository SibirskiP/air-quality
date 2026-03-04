from aq_common.units import from_canonical, to_canonical


def test_mg_to_ug():
    value, unit = to_canonical("PM10", 0.1, "mg/m3")
    assert unit == "ug/m3"
    assert value == 100.0


def test_no2_ppb_roundtrip():
    canonical, _ = to_canonical("NO2", 19.22, "ppb")
    converted = from_canonical("NO2", canonical, "ppb")
    assert converted is not None
    assert abs(converted - 19.22) < 0.01

