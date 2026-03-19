import requests
import os
import json
from datetime import datetime, timedelta, timezone

# ===================== 配置 =====================
SENDKEY   = os.getenv("SENDKEY")
UP_MID    = os.getenv("UP_MID")
BV_ID     = os.getenv("BV_ID")

LAST_FILE = "last_comments.json"  # 上次结果
CST       = timezone(timedelta(hours=8))
# =================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": f"https://www.bilibili.com/video/{BV_ID}/"
}

# ------------------------------
# 1. 读取 / 保存上次评论
# ------------------------------
def load_last():
    try:
        if os.path.exists(LAST_FILE):
            with open(LAST_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
    except:
        pass
    return set()

def save_current(ids):
    try:
        with open(LAST_FILE, "w", encoding="utf-8") as f:
            json.dump(list(ids), f, ensure_ascii=False)
    except:
        pass

# ------------------------------
# 2. BV 转 aid
# ------------------------------
def bv_to_aid(bv):
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv}"
        data = requests.get(url, headers=HEADERS, timeout=10).json()
        return data["data"]["aid"] if data.get("code") == 0 else None
    except:
        return None

# ------------------------------
# 3. 获取当前所有 UP 评论（带ID）
# ------------------------------
def get_current_up_comments(aid):
    target = int(UP_MID)
    items = []
    ids = set()

    for page in range(1, 6):
        try:
            url = f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&pn={page}&ps=50&sort=2"
            data = requests.get(url, headers=HEADERS, timeout=10).json()
            if data.get("code") != 0:
                break

            replies = data.get("data", {}).get("replies", [])
            if not replies:
                break

            for r in replies:
                rpid = str(r.get("rpid", ""))
                if r.get("mid") == target and rpid:
                    ids.add(rpid)
                    items.append({
                        "id": rpid,
                        "time": datetime.fromtimestamp(r["ctime"], CST).strftime("%m-%d %H:%M"),
                        "text": r["content"]["message"].strip()
                    })

                for sub in r.get("replies", []):
                    subid = str(sub.get("rpid", ""))
                    if sub.get("mid") == target and subid:
                        ids.add(subid)
                        items.append({
                            "id": subid,
                            "time": datetime.fromtimestamp(sub["ctime"], CST).strftime("%m-%d %H:%M"),
                            "text": sub["content"]["message"].strip()
                        })
        except:
            continue
    return items, ids

# ------------------------------
# 4. 只发新增评论
# ------------------------------
def send_new(items):
    if not items:
        print("ℹ️ 无新评论")
        return

    lines = [f"【{it['time']}】{it['text']}" for it in items]
    content = "\n\n".join(lines)
    title = f"🆕 UP 新增评论 {len(items)} 条"

    try:
        requests.post(
            f"https://sctapi.ftqq.com/{SENDKEY}.send",
            data={"title": title, "desp": content, "channel": 9},
            timeout=10
        )
        print("✅ 已推送新评论")
    except:
        print("❌ 推送失败")

# ------------------------------
# 主逻辑
# ------------------------------
if __name__ == "__main__":
    print("=== 5分钟自动监控运行 ===")
    aid = bv_to_aid(BV_ID)
    if not aid:
        print("❌ BV转换失败")
        exit()

    last_ids = load_last()
    current_items, current_ids = get_current_up_comments(aid)

    # 找出新增
    new_items = [it for it in current_items if it["id"] not in last_ids]
    send_new(new_items)

    # 覆盖旧记录
    save_current(current_ids)
