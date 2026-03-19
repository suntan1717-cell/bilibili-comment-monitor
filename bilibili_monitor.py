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
WECOM_KEY = os.getenv("WECOM_KEY")

# 新增：记录上次推送时间的文件
LAST_FILE = "last_comments.json"
LAST_TIME_FILE = "last_push_time.json"
CST       = timezone(timedelta(hours=8))
# =================================================

# 基础请求头
def get_headers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{BV_ID}/",
        "Cookie": BILI_COOKIE,
        "Accept": "application/json, text/plain, */*",
    }
    return headers

# ------------------------------
# 新增：读取/保存上次推送时间
# ------------------------------
def load_last_push_time():
    """读取上次推送的时间戳，无则返回0（首次运行）"""
    try:
        if os.path.exists(LAST_TIME_FILE):
            with open(LAST_TIME_FILE, "r", encoding="utf-8") as f:
                return int(json.load(f))
    except:
        pass
    return 0

def save_last_push_time(timestamp):
    """保存本次推送的时间戳（当前时间）"""
    try:
        with open(LAST_TIME_FILE, "w", encoding="utf-8") as f:
            json.dump(timestamp, f)
    except:
        pass

# ------------------------------
# 读取/保存上次评论ID
# ------------------------------
def load_last_comment_ids():
    try:
        if os.path.exists(LAST_FILE):
            with open(LAST_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
    except:
        pass
    return set()

def save_current_comment_ids(ids):
    try:
        with open(LAST_FILE, "w", encoding="utf-8") as f:
            json.dump(list(ids), f, ensure_ascii=False)
    except:
        pass

# ------------------------------
# BV 转 aid
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
# 抓取评论（按上次推送时间筛选）
# ------------------------------
def get_up_comments(aid):
    target_mid = int(UP_MID) if (UP_MID and UP_MID.isdigit()) else 0
    up_comments = []
    up_ids = set()
    total_comments = 0

    # 读取上次推送时间
    last_push_ts = load_last_push_time()
    last_push_time = datetime.fromtimestamp(last_push_ts, CST) if last_push_ts > 0 else "首次运行"
    print(f"🔍 目标UP主ID：{target_mid} | 上次推送时间：{last_push_time}")

    # 抓前10页，ps=20
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

            # 遍历评论（按时间筛选）
            for r in replies:
                r_mid = r.get("mid", 0) if isinstance(r, dict) else 0
                rpid = str(r.get("rpid", "")) if isinstance(r, dict) else ""
                r_ctime = r.get("ctime", 0) if isinstance(r, dict) else 0
                r_content = r.get("content", {}) if isinstance(r, dict) else {}
                r_msg = r_content.get("message", "").strip() if isinstance(r_content, dict) else ""

                # 核心：只保留「上次推送时间之后」的评论
                if last_push_ts > 0 and r_ctime < last_push_ts:
                    print(f"⏩ 第{page}页已到上次推送前的评论，停止抓取")
                    return up_comments, up_ids

                # 筛选UP主评论
                if r_mid == target_mid and rpid and r_msg:
                    comment_time = datetime.fromtimestamp(r_ctime, CST).strftime("%m-%d %H:%M:%S")
                    up_comments.append({
                        "id": rpid,
                        "time": comment_time,
                        "ts": r_ctime,  # 保存时间戳
                        "text": r_msg
                    })
                    up_ids.add(rpid)
                    print(f"✅ 抓到UP主新评论：[{comment_time}] {r_msg[:20]}...")

                # 楼中楼评论
                subs = r.get("replies", []) if isinstance(r, dict) else []
                if not isinstance(subs, list):
                    subs = []
                for sub in subs:
                    sub_mid = sub.get("mid", 0) if isinstance(sub, dict) else 0
                    sub_rpid = str(sub.get("rpid", "")) if isinstance(sub, dict) else ""
                    sub_ctime = sub.get("ctime", 0) if isinstance(sub, dict) else 0
                    sub_content = sub.get("content", {}) if isinstance(sub, dict) else {}
                    sub_msg = sub_content.get("message", "").strip() if isinstance(sub_content, dict) else ""

                    if last_push_ts > 0 and sub_ctime < last_push_ts:
                        continue
                    if sub_mid == target_mid and sub_rpid and sub_msg:
                        comment_time = datetime.fromtimestamp(sub_ctime, CST).strftime("%m-%d %H:%M:%S")
                        up_comments.append({
                            "id": sub_rpid,
                            "time": comment_time,
                            "ts": sub_ctime,
                            "text": sub_msg
                        })
                        up_ids.add(sub_rpid)
                        print(f"✅ 抓到UP主楼中楼新评论：[{comment_time}] {sub_msg[:20]}...")

            if page_comment_count < 20:
                print(f"ℹ️ 第{page}页评论不足20条，无更多评论")
                break

        except Exception as e:
            print(f"⚠️ 第{page}页抓取异常：{str(e)[:50]}")
            continue

    print(f"\n📊 抓取总结：")
    print(f"   - 总评论数：{total_comments}")
    print(f"   - 上次推送后UP主新增评论数：{len(up_comments)}")
    return up_comments, up_ids

# ------------------------------
# Wecom酱推送
# ------------------------------
def send_wecom(new_comments):
    if not new_comments:
        print("ℹ️ 无新增评论，不推送")
        return
    
    title = f"🆕 UP主新增评论 {len(new_comments)} 条"
    content = "\n\n".join([f"【{c['time']}】{c['text']}" for c in new_comments])
    
    if not WECOM_KEY:
        print("❌ 未配置Wecom酱Key，推送失败")
        return
    
    try:
        url = f"https://wecomchan.com/{WECOM_KEY}.send"
        data = {"title": title, "desp": content, "type": "markdown"}
        resp = requests.post(url, data=data, timeout=10)
        
        if resp.status_code == 200:
            print("✅ Wecom酱推送成功！")
            # 推送成功后，保存当前时间戳
            current_ts = int(time.time())
            save_last_push_time(current_ts)
            print(f"📌 已保存本次推送时间：{datetime.fromtimestamp(current_ts, CST)}")
        else:
            print(f"❌ 推送失败：{resp.text}")
    except Exception as e:
        print(f"❌ Wecom酱推送异常：{str(e)}")

# ------------------------------
# 主逻辑
# ------------------------------
if __name__ == "__main__":
    current_time = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== 🔔 B站评论监控启动 | {current_time} ===")
    print(f"配置：UP_MID={UP_MID}，BV={BV_ID}，Cookie={bool(BILI_COOKIE)}")

    # 基础校验
    if not UP_MID or not UP_MID.isdigit():
        print("❌ UP_MID必须是纯数字！")
        exit()
    if not BV_ID or not BV_ID.startswith("BV"):
        print("❌ BV_ID必须以BV开头！")
        exit()

    # BV转aid
    aid = bv_to_aid(BV_ID)
    if not aid:
        print("❌ BV转换失败！")
        exit()
    print(f"✅ BV={BV_ID} → OID={aid}")

    # 抓取新增评论（按上次推送时间）
    new_comments, current_ids = get_up_comments(aid)

    # 推送
    send_wecom(new_comments)

    # 保存本次评论ID（备用）
    save_current_comment_ids(current_ids)
    print("=== 🎯 监控结束 ===\n")
