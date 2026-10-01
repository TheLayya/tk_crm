import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app.services.encryption_service import EncryptedType


@pytest.mark.parametrize('dialect,stored,modeled,expected', [
    ('sqlite', sa.Text(), EncryptedType(), False),
    ('sqlite', sa.String(), EncryptedType(), False),
    ('sqlite', sa.String(10), EncryptedType(), None),
    ('sqlite', sa.Integer(), EncryptedType(), None),
    ('sqlite', sa.String(16), sa.Enum('idle', 'disabled'), False),
    ('sqlite', sa.String(4), sa.Enum('idle', 'disabled'), None),
    ('sqlite', sa.Integer(), sa.Enum('idle', 'disabled'), None),
    ('sqlite', sa.String(4), sa.String(8), None),
    ('postgresql', sa.Text(), EncryptedType(), None),
])
def test_sqlite_type_compatibility_does_not_hide_real_changes(dialect, stored, modeled, expected):
    source = (Path(__file__).resolve().parents[1] / 'alembic/env.py').read_text(encoding='utf-8')
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == '_compare_type')
    namespace = {'sa': sa, 'EncryptedType': EncryptedType}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'alembic/env.py', 'exec'), namespace)
    context = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    assert namespace['_compare_type'](context, None, None, stored, modeled) is expected
