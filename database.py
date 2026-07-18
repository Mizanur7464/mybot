import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "expenses.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL DEFAULT 'অন্যান্য',
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                user_id INTEGER PRIMARY KEY,
                monthly_budget REAL NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


def add_expense(user_id: int, amount: float, category: str, note: str = "") -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, note, now),
        )
        conn.commit()
        return cur.lastrowid


def get_today_expenses(user_id: int) -> list[sqlite3.Row]:
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM expenses
            WHERE user_id = ? AND date(created_at) = ?
            ORDER BY id DESC
            """,
            (user_id, today),
        ).fetchall()


def get_month_expenses(user_id: int, year: int | None = None, month: int | None = None) -> list[sqlite3.Row]:
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    prefix = f"{year:04d}-{month:02d}"
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM expenses
            WHERE user_id = ? AND strftime('%Y-%m', created_at) = ?
            ORDER BY id DESC
            """,
            (user_id, prefix),
        ).fetchall()


def get_expense(user_id: int, expense_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()


def update_expense(
    user_id: int,
    expense_id: int,
    amount: float | None = None,
    category: str | None = None,
    note: str | None = None,
) -> bool:
    row = get_expense(user_id, expense_id)
    if not row:
        return False
    new_amount = amount if amount is not None else row["amount"]
    new_category = category if category is not None else row["category"]
    new_note = note if note is not None else row["note"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE expenses SET amount = ?, category = ?, note = ? WHERE id = ? AND user_id = ?",
            (new_amount, new_category, new_note, expense_id, user_id),
        )
        conn.commit()
    return True


def delete_expense(user_id: int, expense_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def set_budget(user_id: int, amount: float) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO budgets (user_id, monthly_budget) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET monthly_budget = excluded.monthly_budget
            """,
            (user_id, amount),
        )
        conn.commit()


def get_budget(user_id: int) -> float:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT monthly_budget FROM budgets WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return float(row["monthly_budget"]) if row else 0.0


def sum_amounts(rows: list[sqlite3.Row]) -> float:
    return sum(float(r["amount"]) for r in rows)


def category_breakdown(rows: list[sqlite3.Row]) -> dict[str, float]:
    result: dict[str, float] = {}
    for r in rows:
        cat = r["category"]
        result[cat] = result.get(cat, 0.0) + float(r["amount"])
    return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
