from __future__ import annotations

from sqlalchemy import select

from fincore.core.security import hash_password
from fincore.db.models import (
    FeeRule,
    Membership,
    Organization,
    OrganizationType,
    Role,
    User,
    VerificationStatus,
    Wallet,
)
from fincore.db.session import SessionLocal
from fincore.services.bootstrap import ensure_rbac
from fincore.services.financial import (
    complete_deposit,
    create_deposit,
    create_payment,
    create_transfer,
    request_withdrawal,
)
from fincore.services.ledger import ensure_wallet_account

PASSWORD = "FinCore-Dev-2026!"


def main() -> None:
    with SessionLocal() as db:
        if db.scalar(select(Organization).where(Organization.name == "FinCore Platform")):
            print("Development seed already exists; no changes made.")
            return
        ensure_rbac(db)
        platform = Organization(
            name="FinCore Platform",
            type=OrganizationType.PLATFORM,
            default_currency="PKR",
            verification_status=VerificationStatus.VERIFIED,
        )
        customer_org = Organization(
            name="Northstar Design Studio",
            type=OrganizationType.CUSTOMER,
            default_currency="PKR",
            contact_email="customer@fincore.example",
            verification_status=VerificationStatus.VERIFIED,
        )
        merchant_org = Organization(
            name="Atlas Commerce PK",
            type=OrganizationType.MERCHANT,
            default_currency="PKR",
            contact_email="merchant@fincore.example",
            verification_status=VerificationStatus.VERIFIED,
        )
        db.add_all([platform, customer_org, merchant_org])
        db.flush()

        users = {
            "admin": User(
                email="admin@fincore.example",
                full_name="Ayesha Khan",
                password_hash=hash_password(PASSWORD),
                email_verified=True,
            ),
            "ops": User(
                email="ops@fincore.example",
                full_name="Bilal Ahmed",
                password_hash=hash_password(PASSWORD),
                email_verified=True,
            ),
            "merchant": User(
                email="merchant@fincore.example",
                full_name="Sara Malik",
                password_hash=hash_password(PASSWORD),
                email_verified=True,
            ),
            "customer": User(
                email="customer@fincore.example",
                full_name="Hamza Ali",
                password_hash=hash_password(PASSWORD),
                email_verified=True,
            ),
        }
        db.add_all(users.values())
        db.flush()
        roles = {role.name: role for role in db.scalars(select(Role)).all()}
        db.add_all(
            [
                Membership(
                    organization_id=platform.id,
                    user_id=users["admin"].id,
                    role_id=roles["platform_administrator"].id,
                ),
                Membership(
                    organization_id=platform.id,
                    user_id=users["ops"].id,
                    role_id=roles["operations_manager"].id,
                ),
                Membership(
                    organization_id=merchant_org.id,
                    user_id=users["merchant"].id,
                    role_id=roles["merchant_administrator"].id,
                ),
                Membership(
                    organization_id=customer_org.id,
                    user_id=users["customer"].id,
                    role_id=roles["customer"].id,
                ),
            ]
        )
        customer_wallet = Wallet(organization_id=customer_org.id, currency="PKR")
        merchant_wallet = Wallet(organization_id=merchant_org.id, currency="PKR")
        db.add_all([customer_wallet, merchant_wallet])
        db.flush()
        ensure_wallet_account(db, customer_wallet)
        ensure_wallet_account(db, merchant_wallet)
        db.add_all(
            [
                FeeRule(
                    organization_id=None,
                    operation_type="merchant_payment",
                    currency="PKR",
                    percentage_bps=250,
                    minimum_fee=100,
                ),
                FeeRule(
                    organization_id=None,
                    operation_type="transfer",
                    currency="PKR",
                    fixed_amount=25,
                ),
                FeeRule(
                    organization_id=None,
                    operation_type="withdrawal",
                    currency="PKR",
                    fixed_amount=100,
                ),
                FeeRule(
                    organization_id=None,
                    operation_type="deposit",
                    currency="PKR",
                ),
            ]
        )
        db.commit()

        customer_deposit = create_deposit(
            db,
            organization_id=customer_org.id,
            actor_id=users["customer"].id,
            wallet_id=customer_wallet.id,
            amount=2_000_000,
            currency="PKR",
            reference="SEED-CUSTOMER-FUNDING",
        )
        complete_deposit(
            db,
            deposit_id=customer_deposit.id,
            actor_id=users["admin"].id,
            authorized_development_confirmation=True,
        )
        merchant_deposit = create_deposit(
            db,
            organization_id=merchant_org.id,
            actor_id=users["merchant"].id,
            wallet_id=merchant_wallet.id,
            amount=500_000,
            currency="PKR",
            reference="SEED-MERCHANT-FUNDING",
        )
        complete_deposit(
            db,
            deposit_id=merchant_deposit.id,
            actor_id=users["admin"].id,
            authorized_development_confirmation=True,
        )
        create_payment(
            db,
            organization_id=customer_org.id,
            actor_id=users["customer"].id,
            customer_wallet_id=customer_wallet.id,
            merchant_wallet_id=merchant_wallet.id,
            amount=125_000,
            currency="PKR",
            reference="ORDER-1007",
            description="Professional design subscription",
            metadata={"order_id": "ORDER-1007", "channel": "seed"},
        )
        create_transfer(
            db,
            organization_id=customer_org.id,
            actor_id=users["customer"].id,
            sender_wallet_id=customer_wallet.id,
            receiver_wallet_id=merchant_wallet.id,
            amount=25_000,
            currency="PKR",
            reference="TRANSFER-1001",
            description="Invoice settlement",
        )
        request_withdrawal(
            db,
            organization_id=merchant_org.id,
            actor_id=users["merchant"].id,
            wallet_id=merchant_wallet.id,
            amount=50_000,
            currency="PKR",
            destination_masked="Bank account •••• 8842",
            reference="PAYOUT-1001",
        )
        db.commit()
        print("FinCore development data created.")
        print(f"Password for all development accounts: {PASSWORD}")
        print("Accounts: admin@fincore.example, ops@fincore.example, merchant@fincore.example, customer@fincore.example")


if __name__ == "__main__":
    main()
