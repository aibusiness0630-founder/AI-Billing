"""
Startup helpers (safe to run on every start):

ensure_schema()    -> adds the new approval columns to the existing `shop`
                      table (db.create_all() does NOT add columns to old
                      tables). Existing shops are marked APPROVED so nobody
                      gets locked out. Also adds product units (kg / litre)
                      and makes stock / quantity columns decimal.
seed_superadmin()  -> creates the first Super Admin from environment
                      variables SUPERADMIN_USERNAME / SUPERADMIN_PASSWORD,
                      only when no Super Admin exists yet.
"""
import os

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash


def ensure_schema(db):
    try:
        insp = inspect(db.engine)

        if "shop" not in insp.get_table_names():
            return

        cols = {c["name"] for c in insp.get_columns("shop")}
        stmts = []

        if "approval_status" not in cols:
            stmts.append(
                "ALTER TABLE shop ADD COLUMN approval_status "
                "VARCHAR(20) DEFAULT 'APPROVED'"
            )
        if "approved_at" not in cols:
            stmts.append("ALTER TABLE shop ADD COLUMN approved_at TIMESTAMP")
        if "rejection_reason" not in cols:
            stmts.append(
                "ALTER TABLE shop ADD COLUMN rejection_reason VARCHAR(255)"
            )

        with db.engine.begin() as conn:
            for stmt in stmts:
                conn.execute(text(stmt))
            conn.execute(text(
                "UPDATE shop SET approval_status = 'APPROVED' "
                "WHERE approval_status IS NULL"
            ))

        if stmts:
            print("[schema] shop approval columns added")

    except Exception as e:
        print("[schema] ensure_schema failed:", e)

    ensure_units_schema(db)


# columns that must hold decimals (0.75 kg, 12.5 kg stock ...)
DECIMAL_COLUMNS = [
    ("product", "stock"),
    ("product", "min_stock"),
    ("product", "max_stock"),
    ("invoice_item", "quantity"),
    ("stock_movement", "quantity_change"),
    ("purchase_item", "quantity"),
]


def ensure_units_schema(db):
    """
    1. product.unit and invoice_item.unit columns (db.create_all() cannot
       add columns to old tables).
    2. On PostgreSQL: whole-number quantity columns -> DOUBLE PRECISION.
       (SQLite accepts decimals in these columns as they are.)
    Safe to run on every start; each step is skipped when already done.
    """
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())

        # ---- 1. unit columns ----
        added = []
        for table in ("product", "invoice_item"):
            if table not in tables:
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if "unit" not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE %s ADD COLUMN unit VARCHAR(20)" % table
                    ))
                added.append(table)

        if "product" in tables:
            with db.engine.begin() as conn:
                conn.execute(text(
                    "UPDATE product SET unit = 'pcs' WHERE unit IS NULL"
                ))

        if added:
            print("[schema] unit column added to:", ", ".join(added))

        # ---- 2. decimal quantities (PostgreSQL only) ----
        if db.engine.dialect.name != "postgresql":
            return

        for table, column in DECIMAL_COLUMNS:
            if table not in tables:
                continue
            try:
                with db.engine.begin() as conn:
                    row = conn.execute(text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_name = :t AND column_name = :c "
                        "AND table_schema = current_schema()"
                    ), {"t": table, "c": column}).fetchone()

                    if row and row[0] in ("integer", "smallint", "bigint"):
                        conn.execute(text(
                            "ALTER TABLE %s ALTER COLUMN %s "
                            "TYPE DOUBLE PRECISION USING %s::double precision"
                            % (table, column, column)
                        ))
                        print("[schema] %s.%s is now decimal" % (table, column))
            except Exception as e:
                print("[schema] could not change %s.%s: %s" % (table, column, e))

    except Exception as e:
        print("[schema] ensure_units_schema failed:", e)


def seed_superadmin(db):
    try:
        from app.models import SuperAdmin

        username = (os.environ.get("SUPERADMIN_USERNAME") or "").strip()
        password = os.environ.get("SUPERADMIN_PASSWORD") or ""

        if not username or not password:
            return

        if len(password) < 8:
            print("[superadmin] SUPERADMIN_PASSWORD must be 8+ characters")
            return

        existing = SuperAdmin.query.first()

        if existing:
            # .env / Render environment is the source of truth:
            # change the values there + restart = login changes.
            changed = False

            if existing.username != username:
                taken = SuperAdmin.query.filter(
                    SuperAdmin.username == username,
                    SuperAdmin.id != existing.id
                ).first()
                if taken:
                    print("[superadmin] username already used by another admin")
                    return
                existing.username = username
                changed = True

            if not check_password_hash(existing.password, password):
                existing.password = generate_password_hash(password)
                changed = True

            if changed:
                db.session.commit()
                print("[superadmin] login updated from environment:", username)
            return

        db.session.add(SuperAdmin(
            username=username,
            password=generate_password_hash(password)
        ))
        db.session.commit()
        print("[superadmin] first super admin created:", username)

    except Exception as e:
        db.session.rollback()
        print("[superadmin] seed failed:", e)