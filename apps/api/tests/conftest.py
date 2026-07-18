from __future__ import annotations

import os
from collections.abc import Generator

os.environ["FINCORE_ENV"] = "test"
os.environ["FINCORE_DATABASE_URL"] = "sqlite://"
os.environ["FINCORE_PROVIDER_MODE"] = "development"
os.environ["FINCORE_JWT_SECRET"] = "test-secret-that-is-at-least-thirty-two-chars"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from fincore.core.security import hash_password
from fincore.db.base import Base
from fincore.db.models import (
    Membership,
    Organization,
    OrganizationType,
    Role,
    User,
    Wallet,
)
from fincore.db.session import get_db
from fincore.main import app
from fincore.services.bootstrap import ensure_rbac
from fincore.services.ledger import ensure_wallet_account

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def reset_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(db: Session) -> dict[str, object]:
    ensure_rbac(db)
    platform = Organization(name="Platform", type=OrganizationType.PLATFORM, default_currency="PKR")
    customer_org = Organization(name="Customer Org", type=OrganizationType.CUSTOMER, default_currency="PKR")
    merchant_org = Organization(name="Merchant Org", type=OrganizationType.MERCHANT, default_currency="PKR")
    other_org = Organization(name="Other Org", type=OrganizationType.CUSTOMER, default_currency="PKR")
    db.add_all([platform, customer_org, merchant_org, other_org])
    db.flush()
    customer = User(email="customer@test.example", full_name="Customer", password_hash=hash_password("StrongPassword!123"))
    merchant = User(email="merchant@test.example", full_name="Merchant", password_hash=hash_password("StrongPassword!123"))
    admin = User(email="admin@test.example", full_name="Admin", password_hash=hash_password("StrongPassword!123"))
    other = User(email="other@test.example", full_name="Other", password_hash=hash_password("StrongPassword!123"))
    db.add_all([customer, merchant, admin, other])
    db.flush()
    roles = {role.name: role for role in db.scalars(select(Role)).all()}
    db.add_all(
        [
            Membership(organization_id=customer_org.id, user_id=customer.id, role_id=roles["customer"].id),
            Membership(organization_id=merchant_org.id, user_id=merchant.id, role_id=roles["merchant_administrator"].id),
            Membership(organization_id=platform.id, user_id=admin.id, role_id=roles["platform_administrator"].id),
            Membership(organization_id=other_org.id, user_id=other.id, role_id=roles["customer"].id),
        ]
    )
    customer_wallet = Wallet(organization_id=customer_org.id, currency="PKR")
    merchant_wallet = Wallet(organization_id=merchant_org.id, currency="PKR")
    other_wallet = Wallet(organization_id=other_org.id, currency="PKR")
    db.add_all([customer_wallet, merchant_wallet, other_wallet])
    db.flush()
    for wallet in [customer_wallet, merchant_wallet, other_wallet]:
        ensure_wallet_account(db, wallet)
    db.commit()
    return {
        "platform": platform,
        "customer_org": customer_org,
        "merchant_org": merchant_org,
        "other_org": other_org,
        "customer": customer,
        "merchant": merchant,
        "admin": admin,
        "other": other,
        "customer_wallet": customer_wallet,
        "merchant_wallet": merchant_wallet,
        "other_wallet": other_wallet,
    }
