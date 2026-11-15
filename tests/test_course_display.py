import pytest
from astock.course_display import LabDisplay


def test_display_limits_and_missing_points():
    display = LabDisplay()
    display.lines({'price': [1, None, 2, float('inf')]})
    assert display.items[0]['series']['price'] == [1, None, 2, None]
    display.table([[str(i)] for i in range(201)], headers=['时间'])
    assert len(display.items[1]['rows']) == 200
    assert display.items[1]['truncated']
    display.lines({'long': list(range(5001))})
    assert len(display.items[2]['series']['long']) == 5000
    assert display.items[2]['truncated']
    with pytest.raises(ValueError):
        display.lines({})
def test_iterable_table_stops_reading_after_display_limit():
    from astock.course_display import LabDisplay
    from itertools import repeat
    lab = LabDisplay()
    lab.table(repeat(range(50)))
    assert len(lab.items[0]['rows']) == 200
    assert len(lab.items[0]['rows'][0]) == 20
    assert lab.items[0]['truncated']

