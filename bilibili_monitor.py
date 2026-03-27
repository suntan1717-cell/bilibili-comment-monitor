import requests
import os
import json
import random
import time
from datetime import datetime, timedelta, timezone

# ===================== 配置 =====================
UP_MID = os.getenv("UP_MID")
BV_ID = os.getenv("BV_ID")
BILI_COOKIE = os.getenv("BILI_COOKIE", "")
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK")

LAST_IDS_FILE = "last_comment_ids.json"
LAST_TIME_FILE = "last_push_time.json"

CST = timezone(timedelta(hours=8))
MAX_MSG_LEN = 1800   # 企业微信单条消息限制（保守值）
# =================================================

def get_headers():
    return {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://www.bilibili.com/video/{BV_ID}/",
        "Cookie": BILI_COOKIE,
    }

# ------------------------------
# ID 去重
# ------------------------------
def load_last_ids():
    try:
        if os.path.exists(LAST_IDS_FILE):
            with open(LAST_IDS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
    except:
        pass
    return set()

def save_last_ids(ids):
    with open(LAST_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f, ensure_ascii=False)

# ------------------------------
# 时间记录
# ------------------------------
def save_last_push_time(ts):
    with open(LAST_TIME_FILE, "w", encoding="utf-8") as f:
        json.dump(ts, f)

# ------------------------------
# BV → aid
# ------------------------------
def bv_to_aid(bv):
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv}"
    resp = requests.get(url, headers=get_headers(), timeout=10)
    data = resp.json()
    return data["data"]["aid"] if data.get("code") == 0 else None

# ------------------------------
# 抓评论（只扫前3页，够用了）
# ------------------------------
def get_up_comments(aid):
    target_mid = int(UP_MID)
    last_ids = load_last_ids()

    new_comments = []

    for page in range(1, 4):
        time.sleep(random.uniform(1, 2))
        url = f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&pn={page}&ps=20&sort=2"
        resp = requests.get(url, headers=get_headers(), timeout=10)
        data = resp.json()

        replies = data.get("data", {}).get("replies", []) or []

        for r in replies:
            rpid = str(r.get("rpid", ""))
            mid = r.get("mid", 0)

            if rpid in last_ids:
                continue

            if mid == target_mid:
                msg = r.get("content", {}).get("message", "").strip()
                ctime = r.get("ctime", 0)

                if msg:
                    new_comments.append({
                        "id": rpid,
                        "time": datetime.fromtimestamp(ctime, CST).strftime("%m-%d %H:%M"),
                        "text": msg
                    })

            # 楼中楼
            for sub in r.get("replies", []) or []:
                sub_id = str(sub.get("rpid", ""))
                sub_mid = sub.get("mid", 0)

                if sub_id in last_ids:
                    continue

                if sub_mid == target_mid:
                    msg = sub.get("content", {}).get("message", "").strip()
                    ctime = sub.get("ctime", 0)

                    if msg:
                        new_comments.append({
                            "id": sub_id,
                            "time": datetime.fromtimestamp(ctime, CST).strftime("%m-%d %H:%M"),
                            "text": msg
                        })

    return new_comments

# ------------------------------
# 企业微信推送（完整版）
# ------------------------------
def send_wecom(new_comments):
    if not new_comments:
        print("ℹ️ 无新增评论")
        return

    if not WECOM_WEBHOOK:
        print("❌ 未配置 WECOM_WEBHOOK")
        return

    # 合并内容
    lines = []
    for c in new_comments:
        text = c["text"].replace("\n", " ")
        lines.append(f"【{c['time']}】{text}")

    content = "\n".join(lines)

    # 超长截断
    if len(content) > MAX_MSG_LEN:
        content = content[:MAX_MSG_LEN] + "\n...(已截断)"

    data = {
        "msgtype": "text",
        "text": {
            "content": f"🆕 UP主新评论 {len(new_comments)} 条\n\n{content}"
        }
    }

    try:
        resp = requests.post(WECOM_WEBHOOK, json=data, timeout=10)
        if resp.status_code == 200:
            print("✅ 企业微信推送成功")
        else:
            print(f"❌ 推送失败: {resp.text}")
    except Exception as e:
        print(f"❌ 推送异常: {e}")

# ------------------------------
# 主流程（关键：先存ID再推送）
# ------------------------------
if __name__ == "__main__":
    print("=== 🔔 开始监控 ===")

    aid = bv_to_aid(BV_ID)
    if not aid:
        print("❌ BV转换失败")
        exit()

    new_comments = get_up_comments(aid)

    if new_comments:
        last_ids = load_last_ids()
        new_ids = {c["id"] for c in new_comments}

        # ✅ 先保存（避免重复）
        last_ids.update(new_ids)
        save_last_ids(last_ids)

        # ✅ 再推送
        send_wecom(new_comments)

        save_last_push_time(int(time.time()))
        print(f"📌 新增 {len(new_ids)} 条")
    else:
        print("ℹ️ 没有新评论")

    print("=== 🎯 结束 ===")
