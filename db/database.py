import os
import uuid
import json
from datetime import datetime

import pymysql

from config import OWNER_ID, ALL_PERMS, REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS


def get_db():
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10
    )

def ensure_tables():
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                # Admins table
                c.execute("""
                    CREATE TABLE IF NOT EXISTS admins (
                        user_id    BIGINT PRIMARY KEY,
                        username   VARCHAR(255) DEFAULT NULL,
                        perms      TEXT NOT NULL DEFAULT '[]',
                        added_at   DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Referrals table
                # referred_by = user_id of the person who shared the link
                c.execute("""
                    CREATE TABLE IF NOT EXISTS referrals (
                        id           BIGINT AUTO_INCREMENT PRIMARY KEY,
                        referrer_id  BIGINT NOT NULL,
                        referee_id   BIGINT NOT NULL UNIQUE,
                        rewarded     TINYINT(1) DEFAULT 0,
                        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_referrer (referrer_id)
                    )
                """)
                # Make sure users table has a ref_code column
                try:
                    c.execute("ALTER TABLE users ADD COLUMN ref_code VARCHAR(16) UNIQUE DEFAULT NULL")
                except Exception:
                    pass  # Column already exists
                # Add first_name and last_name columns (if not present)
                try:
                    c.execute("ALTER TABLE users ADD COLUMN first_name VARCHAR(255) DEFAULT NULL")
                except Exception:
                    pass  # Already exists
                try:
                    c.execute("ALTER TABLE users ADD COLUMN last_name VARCHAR(255) DEFAULT NULL")
                except Exception:
                    pass  # Already exists
        finally:
            db.close()
    except Exception as e:
        print(f"[ensure_tables ERROR] {e}")

# ── Backward-compat alias ────────────────────────────────────────
def ensure_admins_table():
    ensure_tables()

# ================= REFERRAL HELPERS =================

def get_or_create_ref_code(uid: int) -> str:
    """Return existing ref_code for uid, or generate and save a new one."""
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT ref_code FROM users WHERE user_id=%s", (uid,))
                row = c.fetchone()
                if row and row.get("ref_code"):
                    return row["ref_code"]
                # Generate a short unique code
                code = uuid.uuid4().hex[:8].upper()
                c.execute("UPDATE users SET ref_code=%s WHERE user_id=%s", (code, uid))
                return code
        finally:
            db.close()
    except Exception as e:
        print(f"[get_or_create_ref_code ERROR] {e}")
        return uuid.uuid4().hex[:8].upper()


def get_referral_count(uid: int) -> int:
    """How many people uid has successfully referred."""
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT COUNT(*) AS c FROM referrals WHERE referrer_id=%s", (uid,))
                return c.fetchone()["c"]
        finally:
            db.close()
    except Exception as e:
        print(f"[get_referral_count ERROR] {e}")
        return 0


def get_rewarded_referral_count(uid: int) -> int:
    """How many reward milestones have already been granted to uid."""
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT COUNT(*) AS c FROM referrals WHERE referrer_id=%s AND rewarded=1", (uid,))
                return c.fetchone()["c"]
        finally:
            db.close()
    except Exception as e:
        print(f"[get_rewarded_referral_count ERROR] {e}")
        return 0


def get_uid_by_ref_code(code: str):
    """Return user_id whose ref_code matches, or None."""
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT user_id FROM users WHERE ref_code=%s", (code,))
                row = c.fetchone()
                return row["user_id"] if row else None
        finally:
            db.close()
    except Exception as e:
        print(f"[get_uid_by_ref_code ERROR] {e}")
        return None


def record_referral(referrer_id: int, referee_id: int) -> bool:
    """
    Save the referral link.
    Returns True if this is a NEW referral (not already recorded).
    """
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                # Make sure referrer and referee are different people
                if referrer_id == referee_id:
                    return False
                # Check if referee already has a referral recorded
                c.execute("SELECT id FROM referrals WHERE referee_id=%s", (referee_id,))
                if c.fetchone():
                    return False
                c.execute(
                    "INSERT INTO referrals (referrer_id, referee_id) VALUES (%s, %s)",
                    (referrer_id, referee_id)
                )
                return True
        finally:
            db.close()
    except Exception as e:
        print(f"[record_referral ERROR] {e}")
        return False

# ================= PERMISSION HELPERS =================

def get_sub_admin(uid: int) -> dict | None:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT * FROM admins WHERE user_id=%s", (uid,))
                return c.fetchone()
        finally:
            db.close()
    except Exception as e:
        print(f"[get_sub_admin ERROR] {e}")
        return None

def is_any_admin(uid: int) -> bool:
    if uid == OWNER_ID:
        return True
    return get_sub_admin(uid) is not None

def has_perm(uid: int, perm: str) -> bool:
    if uid == OWNER_ID:
        return True
    row = get_sub_admin(uid)
    if not row:
        return False
    try:
        return perm in json.loads(row["perms"])
    except Exception:
        return False

def get_admin_perms(uid: int) -> list:
    if uid == OWNER_ID:
        return list(ALL_PERMS)
    row = get_sub_admin(uid)
    if not row:
        return []
    try:
        return json.loads(row["perms"])
    except Exception:
        return []

def all_sub_admins() -> list:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT * FROM admins ORDER BY added_at DESC")
                return c.fetchall()
        finally:
            db.close()
    except Exception as e:
        print(f"[all_sub_admins ERROR] {e}")
        return []
