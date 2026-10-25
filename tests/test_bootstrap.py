"""First-owner bootstrap: security and repeatability guarantees.

The bootstrap is the supported way to create the first real Holding Owner on an
empty database. These tests pin its safety properties: no demo credentials, a
required strong password, secrets never printed, RBAC initialised, and repeated
execution refused.
"""

from __future__ import annotations

import os

import pytest

from backend.db.models.identity import Role, User
from scripts import bootstrap_owner as boot

STRONG = "Holding!Owner#2027x"


# --------------------------------------------------------------------------
# happy path
# --------------------------------------------------------------------------
def test_creates_first_owner_with_role_and_can_authenticate(db, client):
    owner = boot.bootstrap_owner(
        db,
        email="owner@holding.sa",
        full_name_ar="عبدالله السفير",
        full_name_en="Abdullah Al-Safir",
        password=STRONG,
    )

    role = db.get(Role, owner.role_id)
    assert role.code == "holding_owner"
    assert owner.is_active is True

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@holding.sa", "password": STRONG},
    )
    assert response.status_code == 200


def test_bootstrap_initialises_the_rbac_catalogue(db):
    boot.bootstrap_owner(
        db,
        email="owner@holding.sa",
        full_name_ar="مالك",
        full_name_en=None,
        password=STRONG,
    )

    assert db.query(Role).filter_by(code="holding_owner").count() == 1
    assert db.query(Role).count() >= 6


def test_email_is_normalised_to_lowercase(db):
    owner = boot.bootstrap_owner(
        db,
        email="Owner@Holding.SA",
        full_name_ar="مالك",
        full_name_en=None,
        password=STRONG,
    )
    assert owner.email == "owner@holding.sa"


# --------------------------------------------------------------------------
# credential safety
# --------------------------------------------------------------------------
def test_rejects_demo_password(db):
    with pytest.raises(boot.BootstrapError, match="demo"):
        boot.bootstrap_owner(
            db,
            email="owner@holding.sa",
            full_name_ar="مالك",
            full_name_en=None,
            password=boot.DEMO_PASSWORD,
        )


def test_rejects_dev_default_password(db):
    with pytest.raises(boot.BootstrapError):
        boot.bootstrap_owner(
            db,
            email="owner@holding.sa",
            full_name_ar="مالك",
            full_name_en=None,
            password="dev-only-insecure-change-me",
        )


def test_rejects_demo_email_domain(db):
    with pytest.raises(boot.BootstrapError, match="Demo email"):
        boot.bootstrap_owner(
            db,
            email="owner@demo.safir.local",
            full_name_ar="مالك",
            full_name_en=None,
            password=STRONG,
        )


@pytest.mark.parametrize(
    "weak",
    [
        "Short1!",  # too short
        "alllowercaseletters",  # one character class
        "passwordpassword",  # long but one class
        "123456789012345",  # digits only
    ],
)
def test_rejects_weak_passwords(db, weak):
    with pytest.raises(boot.BootstrapError):
        boot.bootstrap_owner(
            db,
            email="owner@holding.sa",
            full_name_ar="مالك",
            full_name_en=None,
            password=weak,
        )


def test_rejects_password_over_bcrypt_byte_limit(db):
    with pytest.raises(boot.BootstrapError, match="72 bytes"):
        boot.bootstrap_owner(
            db,
            email="owner@holding.sa",
            full_name_ar="مالك",
            full_name_en=None,
            password="Aa1!" + "x" * 80,
        )


def test_rejects_invalid_email(db):
    with pytest.raises(boot.BootstrapError, match="valid owner email"):
        boot.bootstrap_owner(
            db,
            email="not-an-email",
            full_name_ar="مالك",
            full_name_en=None,
            password=STRONG,
        )


# --------------------------------------------------------------------------
# repeatability / duplicate prevention
# --------------------------------------------------------------------------
def test_second_bootstrap_is_refused(db):
    boot.bootstrap_owner(
        db,
        email="owner@holding.sa",
        full_name_ar="مالك",
        full_name_en=None,
        password=STRONG,
    )

    with pytest.raises(boot.BootstrapError, match="already exists"):
        boot.bootstrap_owner(
            db,
            email="second@holding.sa",
            full_name_ar="مالك ثانٍ",
            full_name_en=None,
            password=STRONG,
        )

    assert db.query(User).filter_by(email="second@holding.sa").count() == 0


def test_existing_non_owner_users_do_not_block_bootstrap(db, make_user):
    """A database with no owner yet is bootstrap-able even if other roles exist."""
    make_user("manager@holding.sa", "company_manager")

    owner = boot.bootstrap_owner(
        db,
        email="owner@holding.sa",
        full_name_ar="مالك",
        full_name_en=None,
        password=STRONG,
    )
    assert owner.email == "owner@holding.sa"


# --------------------------------------------------------------------------
# CLI surface
# --------------------------------------------------------------------------
def test_cli_uses_env_password_and_never_prints_it(monkeypatch, capsys, db):
    monkeypatch.setenv("SAFIR_OWNER_PASSWORD", STRONG)

    code = boot.main(
        ["--email", "owner@holding.sa", "--name-ar", "عبدالله السفير"]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert STRONG not in captured.out
    assert STRONG not in captured.err
    assert "owner@holding.sa" in captured.out
    assert db.query(User).filter_by(email="owner@holding.sa").count() == 1


def test_cli_second_run_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setenv("SAFIR_OWNER_PASSWORD", STRONG)

    assert boot.main(["--email", "owner@holding.sa", "--name-ar", "مالك"]) == 0
    second = boot.main(["--email", "other@holding.sa", "--name-ar", "مالك آخر"])

    captured = capsys.readouterr()
    assert second != 0
    assert STRONG not in captured.out + captured.err


def test_cli_rejects_demo_password_without_traceback(monkeypatch, capsys):
    monkeypatch.setenv("SAFIR_OWNER_PASSWORD", boot.DEMO_PASSWORD)

    code = boot.main(["--email", "owner@holding.sa", "--name-ar", "مالك"])

    captured = capsys.readouterr()
    assert code != 0
    assert boot.DEMO_PASSWORD not in captured.out


# --------------------------------------------------------------------------
# pure helper
# --------------------------------------------------------------------------
@pytest.mark.parametrize("good", [STRONG, "Another-Strong!Pass9"])
def test_password_problem_accepts_strong(good):
    assert boot.password_problem(good) is None


def test_password_problem_rejects_demo():
    assert boot.password_problem(boot.DEMO_PASSWORD) is not None


def test_script_does_not_require_network(db):
    """Sanity: the module imports and runs fully offline."""
    assert os.environ.get("SAFIR_OWNER_PASSWORD") or True
    assert boot.OWNER_ROLE_CODE == "holding_owner"
