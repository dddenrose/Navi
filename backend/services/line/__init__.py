"""LINE Messaging API 整合.

這裡只放沒有相依的常數：conversation_service 也要用，放在子模組會循環 import。
"""

# 加好友時自動建立、沒有網頁帳號的使用者，uid 一律是這個前綴加 LINE user ID
LINE_ONLY_UID_PREFIX = "line_"

# LINE-only 帳號的對話在最後一次寫入後保存的天數，到期由 Firestore TTL 刪除。
# 他們看不到網頁版的對話列表，舊對話對他們沒有用處，留著只會讓管理者看得到。
LINE_ONLY_RETENTION_DAYS = 30


def is_line_only_uid(uid: str) -> bool:
    return uid.startswith(LINE_ONLY_UID_PREFIX)
