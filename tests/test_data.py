from datetime import datetime, timedelta

import pytest

from astock.datasets import ensure_demo, list_datasets, load_dataset, write_dataset
from astock.domain import Bar, CN, dec
from astock.market import parse_tencent
from astock.strategy import TEMPLATES, parameter_schema


def test_demo_round_trip_and_hash_guard(tmp_path):
    ensure_demo(tmp_path)
    datasets = list_datasets(tmp_path)
    assert len(datasets) == 2
    for ds in datasets:
        meta, events = load_dataset(tmp_path, ds["id"])
        assert len(events) == meta["count"]
        assert meta["demo"]
    file = tmp_path / datasets[0]["file"]
    with file.open("ab") as f:
        f.write(b"corruption")
    with pytest.raises(ValueError, match="校验"):
        load_dataset(tmp_path, datasets[0]["id"])


def test_missing_action_blocks_factor_change(tmp_path):
    at = datetime(2026, 11, 12, 15, tzinfo=CN)
    a = Bar("510300.SH", at, dec(4), dec(4), dec(4), dec(4), 10000)
    b = Bar("510300.SH", at + timedelta(days=1), dec(2), dec(2), dec(2), dec(2), 10000, factor=dec(2))
    meta = write_dataset(tmp_path, "factor", [a, b], verified=True)
    with pytest.raises(ValueError, match="权益"):
        load_dataset(tmp_path, meta["id"])


def test_tencent_parser_units_and_timestamps():
    fields = [""] * 88
    for i, v in {1: "浦发银行", 3: "10.40", 4: "10", 6: "2000", 9: "10.39", 10: "50",
                 19: "10.40", 20: "80", 30: "20261113103000", 47: "11", 48: "9"}.items():
        fields[i] = v
    raw = ('v_sh600000="' + "~".join(fields) + '";').encode("gb18030")
    q = parse_tencent(raw)[0]
    assert q.name == "浦发银行"
    assert q.volume == 200000
    assert q.bid_size == 5000
    assert q.time.utcoffset().total_seconds() == 28800
    assert not parse_tencent('v_sh000000="";')


def test_parameter_forms_are_parsed_without_executing_code():
    for template in TEMPLATES.values():
        assert parameter_schema(template["code"])
    assert parameter_schema('raise RuntimeError("do not execute")\nPARAMETERS = {}') == {}
