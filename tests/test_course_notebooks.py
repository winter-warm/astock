import json
from astock.course_library import catalogue, resource
from astock.course_notebooks import export_notebooks, notebook


def test_notebook_sources_are_exact_reader_sources():
    for entry in catalogue():
        if entry['kind'] != 'course' or entry.get('status') != 'published':
            continue
        value = notebook(entry)
        sources = {cell['metadata']['astock_example_id']: cell
                   for cell in value['cells'] if 'astock_example_id' in cell['metadata']}
        for example in entry.get('examples', []):
            code = resource(example['file']).read_text(encoding='utf-8')
            cell = sources[example['id']]
            if example.get('environment') == 'strategy':
                assert cell['cell_type'] == 'markdown'
                assert code in cell['source']
            else:
                assert cell['source'] == code


def test_export_never_overwrites_previous_work(tmp_path):
    entries = [next(e for e in catalogue() if e['id'] == 'q01')]
    first = export_notebooks(tmp_path, entries)
    (first / 'q01.ipynb').write_text('user work', encoding='utf-8')
    second = export_notebooks(tmp_path, entries)
    assert first != second
    assert (first / 'q01.ipynb').read_text(encoding='utf-8') == 'user work'
    assert json.loads((second / 'q01.ipynb').read_text(encoding='utf-8'))['nbformat'] == 4
    assert (second / 'Start-Notebook.ps1').exists()
