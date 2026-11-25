"""reset_password.py: hash por cuenta, desbloqueo y evento de auditoría (control R25).
Ejecutar: pytest -v app/tests/test_reset_password.py
"""
from contextlib import contextmanager

import pytest

from app.scripts import reset_password as rp
from app.security import audit as audit_mod


class Rows:
    def __init__(self, rows): self.rows = rows
    def all(self): return self.rows


class FakeConn:
    def __init__(self, users):
        self.users = users          # {username: user_id}
        self.updates = []           # (user_id, hash)

    def execute(self, statement, params=None):
        sql, params = str(statement), params or {}
        if "SELECT user_id FROM users WHERE username" in sql:
            uid = self.users.get(params["u"])
            return Rows([(uid,)] if uid else [])
        if "SELECT user_id FROM users" in sql:
            return Rows([(uid,) for uid in sorted(self.users.values())])
        if sql.strip().startswith("UPDATE users"):
            assert "failed_attempts = 0" in sql and "locked_until = NULL" in sql
            self.updates.append((params["uid"], params["h"]))
        return Rows([])


@pytest.fixture
def env(monkeypatch, audit_calls):
    conn = FakeConn({"admin.demo": 1, "lgomez": 2, "est.sofia.r": 3})

    class Engine:
        @contextmanager
        def begin(self):
            yield conn

    monkeypatch.setattr(rp, "get_engine", lambda: Engine())
    counter = iter(range(100))
    monkeypatch.setattr(rp.security, "hash_password", lambda pw: f"$argon2id$fake{next(counter)}")
    monkeypatch.setenv("NEW_PASSWORD", "UnaClaveDePrueba2026")
    return conn


def test_short_password_rejected(env, monkeypatch, audit_calls):
    monkeypatch.setenv("NEW_PASSWORD", "corta")
    assert rp.main(["--all"]) == 2
    assert env.updates == [] and audit_calls == []


def test_unknown_user_changes_nothing(env, audit_calls):
    assert rp.main(["--user", "no.existe"]) == 1
    assert env.updates == [] and audit_calls == []


def test_one_user_is_reset_and_audited(env, audit_calls):
    assert rp.main(["--user", "lgomez"]) == 0
    assert [uid for uid, _ in env.updates] == [2]
    action, kw = audit_calls[-1]
    assert action == "user_updated" and kw["user_id"] is None and kw["success"] is True
    assert kw["details"] == {"change": "password_reset_cli", "count": 1, "target_user_id": 2}
    assert "dropped_keys" not in audit_mod._clean_details(kw["details"])


def test_all_users_get_distinct_hashes(env, audit_calls):
    assert rp.main(["--all"]) == 0
    assert [uid for uid, _ in env.updates] == [1, 2, 3]
    assert len({h for _, h in env.updates}) == 3      # una sal distinta por cuenta
    assert audit_calls[-1][1]["details"] == {"change": "password_reset_cli", "count": 3}


def test_user_or_all_is_required(env):
    with pytest.raises(SystemExit):
        rp.main([])
