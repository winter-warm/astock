import pytest
from astock.operations_ui import OperationDialog
from astock.quality_ui import QualityDialog


@pytest.mark.parametrize('kind', ['report', 'compare', 'recover', 'quality'])
def test_preview_never_starts_job_or_creates_files(qtbot, tmp_path, monkeypatch, kind):
    calls = []
    monkeypatch.setattr('astock.data_jobs.DataJobs.start', lambda *args, **kwargs: calls.append(args))
    if kind == 'quality':
        dialog = QualityDialog(tmp_path, 'example', instruction_preview=True)
    else:
        dialog = OperationDialog(tmp_path, kind, instruction_preview=True)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    dialog.start()  # Even a stale callback cannot bypass preview mode.
    assert calls == []
    assert not dialog.retry.isEnabled()
    assert not dialog.open_button.isEnabled()
    dialog.close()
    assert list(tmp_path.iterdir()) == []
