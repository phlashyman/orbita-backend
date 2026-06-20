"""
Seed data script — creates a demo family, admin user, bank accounts,
budget categories, sample transactions, bank statement lines,
brokers, BODIVA instruments, and a sample investment portfolio.
Run: python -m app.utils.seed (from backend directory, with DB running)
"""
import asyncio
from decimal import Decimal
from datetime import date, timedelta

from app.database import AsyncSessionLocal
from app.models.family import Family
from app.models.user import User, UserRole
from app.models.bank_account import BankAccount, AccountType
from app.models.budget_category import BudgetCategory
from app.models.transaction import TransactionManual, TransactionStatus
from app.models.bank_statement import BankStatement, StatementStatus
from app.models.broker import Broker
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.portfolio_holding import PortfolioHolding
from app.models.trade import Trade
from app.dependencies.auth import get_password_hash
from app.utils.seed_portfolio import BROKERS, INSTRUMENTS


async def seed():
    """Insert seed data into the database."""
    async with AsyncSessionLocal() as db:
        # 1. Create Family
        family = Family(name="Família Rosário Jacinto")
        db.add(family)
        await db.flush()  # Get family.id
        print(f"Created family: {family.id}")

        # 2. Create Admin User
        admin = User(
            family_id=family.id,
            name="João Carlos",
            email="joao@orbita.ao",
            hashed_password=get_password_hash("orbita123"),
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.flush()
        print(f"Created admin user: {admin.id} ({admin.email})")

        # 3. Create Bank Accounts
        accounts_data = [
            ("BAI", AccountType.CURRENT, "AOA"),
            ("BFA", AccountType.CURRENT, "AOA"),
            ("BCI", AccountType.SAVINGS, "AOA"),
            ("Caixa", AccountType.CASH, "AOA"),
        ]
        accounts = []
        for bank_name, acc_type, currency in accounts_data:
            acc = BankAccount(
                family_id=family.id,
                bank_name=bank_name,
                account_type=acc_type,
                currency=currency,
            )
            db.add(acc)
            accounts.append(acc)
        await db.flush()
        print(f"Created {len(accounts)} bank accounts")

        # 4. Create Budget Categories (for current month)
        current_month = date.today().replace(day=1)
        categories_data = [
            ("Housing", Decimal("3500000.00")),
            ("Food", Decimal("2000000.00")),
            ("Transport", Decimal("800000.00")),
            ("Health", Decimal("500000.00")),
            ("Education", Decimal("1000000.00")),
            ("Leisure", Decimal("600000.00")),
            ("Utilities", Decimal("450000.00")),
            ("Other", Decimal("300000.00")),
        ]
        categories = []
        for name, projected in categories_data:
            cat = BudgetCategory(
                family_id=family.id,
                name=name,
                projected_amount=projected,
                month_year=current_month,
            )
            db.add(cat)
            categories.append(cat)
        await db.flush()
        print(f"Created {len(categories)} budget categories")

        # 5. Create Sample Transactions
        tx_data = [
            (accounts[0].id, categories[0].id, Decimal("3530000.00"), "Rent payment", date.today() - timedelta(days=2)),
            (accounts[0].id, categories[1].id, Decimal("1870000.00"), "Monthly groceries", date.today() - timedelta(days=3)),
            (accounts[1].id, categories[2].id, Decimal("450000.00"), "Fuel", date.today() - timedelta(days=1)),
            (accounts[1].id, categories[4].id, Decimal("500000.00"), "School fees", date.today() - timedelta(days=5)),
            (accounts[0].id, categories[5].id, Decimal("320000.00"), "Restaurant", date.today() - timedelta(days=1)),
            (accounts[2].id, categories[3].id, Decimal("120000.00"), "Pharmacy", date.today() - timedelta(days=4)),
            (accounts[0].id, None, Decimal("150000.00"), "Cash withdrawal", date.today() - timedelta(days=6)),
            (accounts[1].id, categories[6].id, Decimal("380000.00"), "Electricity bill", date.today() - timedelta(days=7)),
        ]
        for acc_id, cat_id, amount, desc, tx_date in tx_data:
            tx = TransactionManual(
                family_id=family.id,
                user_id=admin.id,
                account_id=acc_id,
                category_id=cat_id,
                amount=amount,
                date=tx_date,
                description=desc,
                status=TransactionStatus.PENDING,
            )
            db.add(tx)
        await db.flush()
        print(f"Created {len(tx_data)} transactions")

        # 6. Create Sample Bank Statement Lines
        stmt_data = [
            (accounts[0].id, "TXN-001-2026", Decimal("3530000.00"), "PAG RENDA", date.today() - timedelta(days=2)),
            (accounts[0].id, "TXN-002-2026", Decimal("1870000.00"), "COMPRA CONTINENTE", date.today() - timedelta(days=3)),
            (accounts[1].id, "TXN-003-2026", Decimal("450000.00"), "ABASTECIMENTO GALP", date.today() - timedelta(days=1)),
            (accounts[1].id, "TXN-004-2026", Decimal("500000.00"), "PAG PROPINA", date.today() - timedelta(days=5)),
            (accounts[0].id, "TXN-005-2026", Decimal("150000.00"), "LEVANTAMENTO ATM", date.today() - timedelta(days=6)),
            (accounts[0].id, "TXN-006-2026", Decimal("420000.00"), "NETFLIX SUBSCRIPTION", date.today() - timedelta(days=1)),
            (accounts[2].id, "TXN-007-2026", Decimal("120000.00"), "FARMACIA SAUDE", date.today() - timedelta(days=4)),
        ]
        for acc_id, bank_txn_id, amount, desc_raw, stmt_date in stmt_data:
            stmt = BankStatement(
                family_id=family.id,
                account_id=acc_id,
                bank_transaction_id=bank_txn_id,
                amount=amount,
                date=stmt_date,
                description_raw=desc_raw,
                status=StatementStatus.UNMATCHED,
            )
            db.add(stmt)

        # 7. Create Brokers
        brokers = []
        for broker_data in BROKERS:
            broker = Broker(**broker_data)
            db.add(broker)
            brokers.append(broker)
        await db.flush()
        print(f"Created {len(brokers)} brokers")

        # 8. Create BODIVA Instruments
        instruments = []
        for instrument_data in INSTRUMENTS:
            instrument = Instrument(**instrument_data)
            db.add(instrument)
            instruments.append(instrument)
        await db.flush()
        print(f"Created {len(instruments)} instruments")

        # 9. Create Sample Portfolio
        portfolio = Portfolio(
            family_id=family.id,
            user_id=admin.id,
            name="Carteira Principal",
            description="Carteira diversificada de rendimento fixo BODIVA",
            portfolio_type="REAL",
            is_default=True,
            total_invested=Decimal("5250000.00"),
            current_value=Decimal("5418750.00"),
            total_return_pct=Decimal("3.21"),
        )
        db.add(portfolio)
        await db.flush()
        print(f"Created portfolio: {portfolio.id}")

        # 10. Create Sample Holdings
        holdings_data = [
            # (instrument_index, broker_index, quantity, avg_buy_price, current_price, current_value)
            (0, 0, 10, Decimal("100000"), Decimal("102500"), Decimal("1025000")),   # OT-2026 via BFA
            (2, 1, 15, Decimal("100000"), Decimal("99500"), Decimal("1492500")),    # OT-2028 via BCI
            (7, 0, 5, Decimal("100000"), Decimal("100500"), Decimal("502500")),      # BFA-2027 via BFA
            (1, 3, 12, Decimal("100000"), Decimal("101200"), Decimal("1214400")),    # OT-2027 via FSDEA
            (4, 0, 10, Decimal("100000"), Decimal("97500"), Decimal("975000")),      # OT-2032 via BFA
            (6, 0, 5, Decimal("50000"), Decimal("50000"), Decimal("250000")),        # CD-BFA via BFA
        ]
        total_pnl = Decimal("0")
        for inst_idx, broker_idx, qty, avg_price, cur_price, cur_val in holdings_data:
            invested = qty * avg_price
            pnl = cur_val - invested
            pnl_pct = (pnl / invested * Decimal("100")) if invested > 0 else Decimal("0")
            total_pnl += pnl

            instrument = instruments[inst_idx]

            holding = PortfolioHolding(
                portfolio_id=portfolio.id,
                instrument_id=instrument.id,
                broker_id=brokers[broker_idx].id,
                quantity=qty,
                avg_buy_price=avg_price,
                current_price=cur_price,
                current_value=cur_val,
                unrealized_pnl=pnl,
                unrealized_pnl_pct=round(pnl_pct, 2),
                next_coupon_date=date(2026, 6, 15) if instrument.frequency_months <= 6 else date(2026, 9, 15),
                next_coupon_amount=(Decimal(str(qty)) * instrument.face_value * (instrument.coupon_rate or Decimal("0")) / Decimal("100") / (Decimal("12") / Decimal(str(instrument.frequency_months if instrument.frequency_months > 0 else 12)))).quantize(Decimal("0.01")),
            )
            db.add(holding)
            await db.flush()

            # Create BUY trade for each holding
            trade = Trade(
                portfolio_id=portfolio.id,
                holding_id=holding.id,
                instrument_id=instrument.id,
                broker_id=brokers[broker_idx].id,
                trade_type="BUY",
                trade_date=date(2025, 10, 15),
                quantity=qty,
                price=avg_price,
                total_amount=invested,
                fees=Decimal("15000.00"),
                notes="Compra inicial",
            )
            db.add(trade)

        # Add a COUPON trade
        coupon_trade = Trade(
            portfolio_id=portfolio.id,
            holding_id=None,
            instrument_id=instruments[0].id,
            broker_id=brokers[0].id,
            trade_type="COUPON",
            trade_date=date(2026, 3, 15),
            quantity=0,
            price=Decimal("0"),
            total_amount=Decimal("156250.00"),
            fees=Decimal("15625.00"),
            notes="Cupao OT-2026",
        )
        db.add(coupon_trade)
        await db.flush()

        print(f"Created {len(holdings_data)} holdings with trades")

        await db.commit()
        print(f"Created {len(stmt_data)} bank statement lines")
        print("\nSeed complete! Login with: joao@orbita.ao / orbita123")


if __name__ == "__main__":
    asyncio.run(seed())
