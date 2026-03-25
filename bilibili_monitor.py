import requests
import os
import json
import random
import time
from datetime import datetime, timedelta, timezone

# ===================== 配置 =====================
UP_MID    = os.getenv("UP_MID")
BV_ID     = os.getenv("BV_ID")
BILI_COOKIE = os.getenv("BILI_COOKIE", "")
SENDKEY   = os.getenv("SENDKEY")

LAST_IDS_FILE = "last_comment_ids.json"  # 只存已推送的评论ID
LAST_TIME_FILE = "last_push_time.json"
CST       = timezone(timedelta(hours=8))
# =================================================

def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://www.bilibili.com/video/{BV_ID}/",
        "Cookie": BILI_COOKIE,
        "Accept": "application/json, text/plain, */*",
    }

# ------------------------------
# 1. 评论ID去重（核心修复）
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
    try:
        with open(LAST_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(ids), f, ensure_ascii=False)
    except:
        pass

# ------------------------------
# 2. 推送时间记录
# ------------------------------
def load_last_push_time():
    try:
        if os.path.exists(LAST_TIME_FILE):
            with open(LAST_TIME_FILE, "r", encoding="utf-8") as f:
                return int(json.load(f))
    except:
        pass
    return 0

def save_last_push_time(timestamp):
    try:
        with open(LAST_TIME_FILE, "w", encoding="utf-8") as f:
            json.dump(timestamp, f)
    except:
        pass

# ------------------------------
# 3. BV 转 aid
# ------------------------------
def bv_to_aid(bv):
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv}"
        resp = requests.get(url, headers=get_headers(), timeout=10)
        data = resp.json()
        return data["data"]["aid"] if data.get("code") == 0 else None
    except:
        return None

# ------------------------------
# 4. 抓取评论（按ID去重）
# ------------------------------
def get_up_comments(aid):
    target_mid = int(UP_MID) if (UP_MID and UP_MID.isdigit()) else 0
    up_comments = []
    last_ids = load_last_ids()
    total_comments = 0

    print(f"🔍 目标UP主ID：{target_mid} | 已推送评论数：{len(last_ids)}")

    for page in range(1, 11):
        time.sleep(random.uniform(1, 3))
        try:
            url = f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&pn={page}&ps=20&sort=2"
            resp = requests.get(url, headers=get_headers(), timeout=10)
            resp.encoding = "utf-8"
            data = resp.json()

            if data.get("code") != 0:
                print(f"⚠️ 第{page}页接口错误：{data.get('message')}")
                continue

            replies = data.get("data", {}).get("replies", [])
            if not isinstance(replies, list):
                replies = []

            page_comment_count = len(replies)
            total_comments += page_comment_count
            print(f"ℹ️ 第{page}页：共{page_comment_count}条评论")

            for r in replies:
                r_mid = r.get("mid", 0) if isinstance(r, dict) else 0
                rpid = str(r.get("rpid", "")) if isinstance(r, dict) else ""
                r_ctime = r.get("ctime", 0) if isinstance(r, dict) else 0
                r_content = r.get("content", {}) if isinstance(r, dict) else {}
                r_msg = r_content.get("message", "").strip() if isinstance(r_content, dict) else ""

                # 核心：用评论ID去重，只要推过就不再推
                if rpid in last_ids:
                    continue
                if r_mid == target_mid and rpid and r_msg:
                    comment_time = datetime.fromtimestamp(r_ctime, CST).strftime("%m-%d %H:%M:%S")
                    up_comments.append({
                        "id": rpid,
                        "time": comment_time,
                        "text": r_msg
                    })
                    print(f"✅ 抓到新评论：[{comment_time}] {r_msg[:20]}...")

                subs = r.get("replies", []) if isinstance(r, dict) else []
                if not isinstance(subs, list):
                    subs = []
                for sub in subs:
                    sub_mid = sub.get("mid", 0) if isinstance(sub, dict) else 0
                    sub_rpid = str(sub.get("rpid", "")) if isinstance(sub, dict) else ""
                    sub_ctime = sub.get("ctime", 0) if isinstance(sub, dict) else 0
                    sub_content = sub.get("content", {}) if isinstance(sub, dict) else {}
                    sub_msg = sub_content.get("message", "").strip() if isinstance(sub_content, dict) else ""

                    if sub_rpid in last_ids:
                        continue
                    if sub_mid == target_mid and sub_rpid and sub_msg:
                        comment_time = datetime.fromtimestamp(sub_ctime, CST).strftime("%m-%d %H:%M:%S")
                        up_comments.append({
                            "id": sub_rpid,
                            "time": comment_time,
                            "text": sub_msg
                        })
                        print(f"✅ 抓到楼中楼新评论：[{comment_time}] {sub_msg[:20]}...")

            if page_comment_count < 20:
                print(f"ℹ️ 第{page}页评论不足20条，无更多评论")
                break

        except Exception as e:
            print(f"⚠️ 第{page}页抓取异常：{str(e)[:50]}")
            continue

    print(f"\n📊 抓取总结：")
    print(f"   - 总评论数：{total_comments}")
    print(f"   - 本次新增评论数：{len(up_comments)}")
    return up_comments

# ------------------------------
# 5. Server酱推送（先存ID，再推送）
# ------------------------------
def send_serverchan(new_comments):
    if not new_comments:
        print("ℹ️ 无新增评论，不推送")
        return set()

    title = f"🆕 UP主新增评论 {len(new_comments)} 条"
    content = "\n\n".join([f"【{c['time']}】{c['text']}" for c in new_comments])
    new_ids = {c["id"] for c in new_comments}

    if not SENDKEY:
        print("❌ 未配置 SENDKEY")
        return set()

    try:
        url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
        data = {"title": title, "desp": content, "channel": 9}
        resp = requests.post(url, data=data, timeout=15)
        resp_data = resp.json()

        if resp.status_code == 200 and resp_data.get("code") == 0:
            print("✅ Server酱推送成功！")
            return new_ids  # 只有推送成功，才返回新ID
        else:
            print(f"❌ 推送失败：{resp_data.get('message')}")
            return set()
    except Exception as e:
        print(f"❌ 推送异常：{e}")
        return set()

# ------------------------------
# 主逻辑
# ------------------------------
if __name__ == "__main__":
    current_time = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== 🔔 B站评论监控启动 | {current_time} ===")

    if not (UP_MID and UP_MID.isdigit() and BV_ID and BV_ID.startswith("BV")):
        print("❌ 配置错误")
        exit()

    aid = bv_to_aid(BV_ID)
    if not aid:
        print("❌ BV转换失败")
        exit()
    print(f"✅ BV={BV_ID} → OID={aid}")

    new_comments = get_up_comments(aid)
    new_ids = send_serverchan(new_comments)

    if new_ids:
        # 推送成功后，合并ID并保存
        last_ids = load_last_ids()
        last_ids.update(new_ids)
        save_last_ids(last_ids)
        save_last_push_time(int(time.time()))
        print(f"📌 已保存{len(new_ids)}条新评论ID")

    print("=== 🎯 监控结束 ===\n")
