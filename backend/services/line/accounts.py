"""LINE 專用帳號 — 沒有綁定的人第一次找 bot 時，自動建帳號並綁定.

官方帳號無法封鎖已加好友的人（LINE 平台限制），所以不在入口設關卡：
誰能用、能用多少，由管理後台的停用狀態與每日額度控制。
"""

import logging

import firebase_admin.auth as firebase_auth

from services import quota_service
from services.firestore_client import _init_firebase
from services.line import client, store

logger = logging.getLogger(__name__)

LINE_ONLY_UID_PREFIX = "line_"


def line_only_uid(line_user_id: str) -> str:
    return f"{LINE_ONLY_UID_PREFIX}{line_user_id}"


def create_line_only_account(line_user_id: str, display_name: str = "") -> str:
    """Create the account for a LINE user without a Navi account, or reuse it; return its uid.

    建 Firebase Auth 使用者（沒有 email 與密碼，無法登入網頁）與 users 文件（預設 free 層）。
    Auth 那筆讓管理後台改 tier 時同步 custom claims、set_tier.py 等腳本照常可用。
    LINE user ID 在同一個 provider 底下固定不變，刪好友再加回來仍是同一個帳號，停用狀態會保留。
    """
    uid = line_only_uid(line_user_id)
    _init_firebase()
    try:
        firebase_auth.get_user(uid)
    except firebase_auth.UserNotFoundError:
        try:
            firebase_auth.create_user(uid=uid, display_name=display_name or None)
            logger.info("Created LINE-only account %s (%s)", uid, display_name or "-")
        except firebase_auth.UidAlreadyExistsError:
            pass  # 同一人的加好友與第一則訊息同時處理，另一邊先建好了
    quota_service.get_or_create_user(uid, display_name=display_name)
    return uid


def link_new_user(line_user_id: str) -> dict:
    """Give an unlinked LINE user an account and link it; return the link now in place.

    若處理期間已被別的事件或腳本綁定，以既有的綁定為準。
    """
    uid = create_line_only_account(line_user_id, client.get_display_name(line_user_id))
    return store.create_link_if_absent(line_user_id, uid)
