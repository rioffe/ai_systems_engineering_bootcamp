# R-16 / F-12: the query console exists and degrades headless + offline. It must
# not block on stdin and must complete (exit 0) with or without a Qt backend.

from rag.corpus import generate_corpus_and_questions
from rag.ui import _import_qt, run_gui


def _fixture(tmp_path, monkeypatch, n_docs=3, n_questions=3):
    monkeypatch.setenv('RAG_CORPUS', str(tmp_path / 'documents'))
    monkeypatch.setenv('RAG_DATASET', str(tmp_path / 'questions.json'))
    generate_corpus_and_questions(out_dir=str(tmp_path), n_docs=n_docs, n_questions=n_questions)
    return tmp_path


def test_import_qt_is_safe():
     # _import_qt returns either a Qt module or None -- it must never raise.
    q = _import_qt()
    assert q is None or hasattr(q, '__name__')


def test_gui_degrades_to_console_without_subcommand(tmp_path, monkeypatch):
    tmp_path = _fixture(tmp_path, monkeypatch)
        # no subcommand -> run_gui prepends `show` and still completes exit 0
    assert run_gui(['--mock', 'on', '--out', str(tmp_path / 'r.json'), '--quiet']) == 0


def test_gui_explicit_show_subcommand(tmp_path, monkeypatch):
    tmp_path = _fixture(tmp_path, monkeypatch)
    assert run_gui(['show', '--mock', 'on', '--out', str(tmp_path / 'r2.json'), '--quiet']) == 0
