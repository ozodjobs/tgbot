import os
import re
from datetime import datetime, timedelta

from config import OWNER_ID, ORDER_LIMIT_PER_MONTH, ORDER_TYPES, menu_basic, menu_premium
from db.database import get_db, all_sub_admins


def has_access(uid: int) -> bool:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT access_until FROM users WHERE user_id=%s", (uid,))
                row = c.fetchone()
            return bool(row and row["access_until"] and row["access_until"] > datetime.now())
        finally:
            db.close()
    except Exception as e:
        print(f"[has_access ERROR] {e}")
        return False

def get_menu(uid: int):
    return menu_premium if has_access(uid) else menu_basic

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[^\w\s\-]', '', name, flags=re.UNICODE).strip()
    return name or "document"

def cleanup_files(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

def format_deadline(deadline_val) -> str:
    if not deadline_val:
        return "—"
    if hasattr(deadline_val, "strftime"):
        return deadline_val.strftime("%d.%m.%Y")
    return str(deadline_val)

def get_order_monthly_count(uid: int) -> int:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                c.execute("SELECT COUNT(*) AS c FROM orders WHERE user_id=%s AND created_at >= %s", (uid, month_start))
                return c.fetchone()["c"]
        finally:
            db.close()
    except Exception as e:
        print(f"[get_order_monthly_count ERROR] {e}")
        return 0

def get_active_order(uid: int):
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute(
                    "SELECT id, type, subject, topic, status FROM orders "
                    "WHERE user_id=%s AND status IN ('pending','in_progress') ORDER BY id DESC LIMIT 1",
                    (uid,)
                )
                return c.fetchone()
        finally:
            db.close()
    except Exception as e:
        print(f"[get_active_order ERROR] {e}")
        return None

def deadline_str_to_date(deadline_str: str) -> str:
    try:
        days = int(deadline_str.split()[0])
        return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        return (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

def get_all_user_ids() -> list:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT user_id FROM users")
                return [r["user_id"] for r in c.fetchall()]
        finally:
            db.close()
    except Exception as e:
        print(f"[get_all_user_ids ERROR] {e}")
        return []

def get_admin_stats() -> dict:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                c.execute("SELECT COUNT(*) AS c FROM users")
                total = c.fetchone()["c"]
                c.execute("SELECT COUNT(*) AS c FROM users WHERE access_until > %s", (datetime.now(),))
                premium = c.fetchone()["c"]
                c.execute("SELECT COUNT(*) AS c FROM payments WHERE status='pending'")
                pending_pay = c.fetchone()["c"]
                c.execute("SELECT COUNT(*) AS c FROM orders WHERE status IN ('pending','in_progress')")
                active_orders = c.fetchone()["c"]
            return {"total": total, "premium": premium, "pending_pay": pending_pay, "active_orders": active_orders}
        finally:
            db.close()
    except Exception as e:
        print(f"[get_admin_stats ERROR] {e}")
        return {"total": 0, "premium": 0, "pending_pay": 0, "active_orders": 0}

def build_admin_text(stats: dict, uid: int) -> str:
    role = "👑 OWNER" if uid == OWNER_ID else "🛡 SUB-ADMIN"
    sub_cnt = len(all_sub_admins())
    base = (
        f"📊 <b>ADMIN PANEL</b>  [{role}]\n\n"
        f"👤 Jami userlar:        <b>{stats['total']}</b>\n"
        f"✅ Premium:             <b>{stats['premium']}</b>\n"
        f"⏳ Kutilayotgan to'lov: <b>{stats['pending_pay']}</b>\n"
        f"📋 Aktiv buyurtmalar:   <b>{stats['active_orders']}</b>\n"
    )
    if uid == OWNER_ID:
        base += f"🛡 Sub-adminlar:        <b>{sub_cnt}</b>\n"
    base += f"\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    return base

def user_submitted_check_today(uid: int) -> bool:
    try:
        db = get_db()
        try:
            with db.cursor() as c:
                since = datetime.now() - timedelta(hours=24)
                c.execute(
                    "SELECT COUNT(*) AS c FROM payments WHERE user_id=%s AND created_at >= %s",
                    (uid, since)
                )
                return c.fetchone()["c"] > 0
        finally:
            db.close()
    except Exception as e:
        print(f"[user_submitted_check_today ERROR] {e}")
        return False
