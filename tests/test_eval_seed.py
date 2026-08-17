"""Integration tests for eval/seed.py — ingests eval/fixtures/ for real (no Fakes;
this is the same ingestion path Phase 1's tests exercise), populates eval_golden.
"""

from sqlalchemy import select

from core.config import get_settings
from db.session import make_engine, make_session_factory, session_scope
from eval.golden_set import GOLDEN_SET
from eval.seed import seed_golden_set
from models import EvalGolden


def _session():
    settings = get_settings()
    engine = make_engine(settings)
    return make_session_factory(engine)


def test_seed_golden_set_writes_one_row_per_golden_entry() -> None:
    session_factory = _session()
    with session_scope(session_factory) as session:
        written = seed_golden_set(session)
        assert written == len(GOLDEN_SET)
        rows = session.execute(select(EvalGolden)).scalars().all()
        assert len(rows) == len(GOLDEN_SET)


def test_seed_golden_set_populates_real_nonempty_chunk_ids() -> None:
    session_factory = _session()
    with session_scope(session_factory) as session:
        seed_golden_set(session)
        rows = session.execute(select(EvalGolden)).scalars().all()
        for row in rows:
            assert len(row.expected_chunk_ids) > 0


def test_seed_golden_set_is_idempotent_on_rerun() -> None:
    session_factory = _session()
    with session_scope(session_factory) as session:
        seed_golden_set(session)
        first_run = {
            row.question: row.expected_chunk_ids
            for row in session.execute(select(EvalGolden)).scalars().all()
        }

        seed_golden_set(session)
        second_run = {
            row.question: row.expected_chunk_ids
            for row in session.execute(select(EvalGolden)).scalars().all()
        }

    assert first_run == second_run
