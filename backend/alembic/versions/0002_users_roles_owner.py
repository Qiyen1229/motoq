"""users roles, security events, vehicle owner

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("app_users") as b:
        b.add_column(sa.Column("role", sa.String(16), nullable=False, server_default="user"))
        b.add_column(sa.Column("status", sa.String(16), nullable=False, server_default="active"))
        b.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))
    # 既有的第一位使用者視為最高權限管理員
    op.execute("UPDATE app_users SET role='admin' WHERE id=(SELECT MIN(id) FROM app_users)")

    with op.batch_alter_table("auth_sessions") as b:
        b.add_column(sa.Column("ip", sa.String(64), nullable=False, server_default=""))
        b.add_column(sa.Column("user_agent", sa.String(255), nullable=False, server_default=""))
        b.add_column(sa.Column("last_seen_at", sa.DateTime(), nullable=True))

    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=False),
        sa.Column("detail", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_security_events_kind", "security_events", ["kind"])
    op.create_index("ix_security_events_created_at", "security_events", ["created_at"])

    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=True),
    )
    # 舊版全域的異常門檻轉為第一位使用者的個人設定
    op.execute(
        "INSERT INTO user_settings (user_id, key, value) "
        "SELECT (SELECT MIN(id) FROM app_users), key, value FROM app_settings "
        "WHERE key='anomaly_drop_pct' AND (SELECT MIN(id) FROM app_users) IS NOT NULL"
    )
    op.execute("DELETE FROM app_settings WHERE key='anomaly_drop_pct'")

    with op.batch_alter_table("vehicles") as b:
        b.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
    op.execute("UPDATE vehicles SET user_id=(SELECT MIN(id) FROM app_users)")
    # 沒有任何使用者卻有車輛（理論上不會發生）：清掉孤兒資料
    op.execute("DELETE FROM vehicles WHERE user_id IS NULL")
    with op.batch_alter_table("vehicles") as b:
        b.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        b.create_foreign_key("fk_vehicles_user_id", "app_users", ["user_id"], ["id"], ondelete="CASCADE")
        b.create_index("ix_vehicles_user_id", ["user_id"])


def downgrade() -> None:
    raise NotImplementedError("不支援降版；請由備份還原")
