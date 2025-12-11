"""
命名服務：生成 Room Code

純計算邏輯，不涉及狀態轉換
"""
import random
import string


def generate_room_code() -> str:
    """
    生成隨機的 6 位大寫字母房間代碼

    範例：ABCDEF, XYZABC

    注意：
    - 不檢查唯一性（由呼叫者負責）
    - 26^6 = 308,915,776 種可能，碰撞機率極低
    """
    return ''.join(random.choices(string.ascii_uppercase, k=6))
