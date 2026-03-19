import requests
import os
import json
import random
import time
from datetime import datetime, timedelta, timezone

# ===================== 配置 =====================
SENDKEY   = os.getenv("SENDKEY")
UP_MID    = os.getenv("UP_MID")
BV_ID     = os.getenv("BV_ID")
BILI_COOKIE = os.getenv("BILI_COOKIE", "")

LAST_FILE = "last_comments.json"
CST       = timezone(timedelta(hours=8))
# =================================================

# 基础请求头（适配B站）
def get_headers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{BV_ID}/",
        "Cookie": BILI_COOKIE,
        "Accept": "application/json, text/plain, */*",
    }
    return headers

# ------------------------------
# 1. 读取/保存上次评论
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
        resp = requests.get(url, headers=get_headers(), timeout=10)
        data = resp.json()
        return data["data"]["aid"] if data.get("code") == 0 else None
    except:
        return None

# ------------------------------
# 3. 抓取评论（适配ps=20参数）
# ------------------------------
def get_up_comments(aid):
    target_mid = int(UP_MID) if (UP_MID and UP_MID.isdigit()) else 0
    up_comments = []
    up_ids = set()
    total_comments = 0

    print(f"🔍 目标UP主ID：{target_mid}，开始抓取评论（ps=20适配B站限制）...")

    # 抓前10页，ps=20（B站强制上限）
    for page in range(1, 11):
        time.sleep(random.uniform(1, 3))
        try:
            # 核心修复：ps=20（B站允许的最大单页条数）
            url = f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&pn={page}&ps=20&sort=2"
            resp = requests.get(url, headers=get_headers(), timeout=10)
            resp.encoding = "utf-8"
            data = resp.json()

            if data.get("code") != 0:
                if data.get("message") == "ps out of bounds":
                    print(f"⚠️ 第{page}页：B站参数限制，已自动适配ps=20仍失败")
                else:
                    print(f"⚠️ 第{page}页接口错误：{data.get('message')}")
                continue

            # 空值防护
            replies = data.get("data", {}).get("replies", [])
            if not isinstance(replies, list):
                replies = []

            page_comment_count = len(replies)
            total_comments += page_comment_count
            print(f"ℹ️ 第{page}页：共{page_comment_count}条评论")

            # 遍历顶层评论
            for r in replies:
                r_mid = r.get("mid", 0) if isinstance(r, dict) else 0
                rpid = str(r.get("rpid", "")) if isinstance(r, dict) else ""
                r_ctime = r.get("ctime", 0) if isinstance(r, dict) else 0
                r_content = r.get("content", {}) if isinstance(r, dict) else {}
                r_msg = r_content.get("message", "").strip() if isinstance(r_content, dict) else ""

                # 调试mid匹配
                print(f"   评论mid={r_mid} → {'匹配UP主' if r_mid == target_mid else '非UP主'}")

                # 筛选UP主评论
                if r_mid == target_mid and rpid and r_msg:
                    up_comments.append({
                        "id": rpid,
                        "time": datetime.fromtimestamp(r_ctime, CST).strftime("%m-%d %H:%M"),
                        "text": r_msg
                    })
                    up_ids.add(rpid)
                    print(f"✅ 抓到UP主评论：[{up_comments[-1]['time']}] {r_msg[:20]}...")

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

                    if sub_mid == target_mid and sub_rpid and sub_msg:
                        up_comments.append({
                            "id": sub_rpid,
                            "time": datetime.fromtimestamp(sub_ctime, CST).strftime("%m-%d %H:%M"),
                            "text": sub_msg
                        })
                        up_ids.add(sub_rpid)
                        print(f"✅ 抓到UP主楼中楼：[{up_comments[-1]['time']}] {sub_msg[:20]}...")

            # 无更多评论则停止
            if page_comment_count < 20:
                print(f"ℹ️ 第{page}页评论不足20条，无更多评论")
                break

        except Exception as e:
            print(f"⚠️ 第{page}页抓取异常：{str(e)[:50]}")
            continue

    # 去重
    unique_comments = []
    seen = set()
    for c in up_comments:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique_comments.append(c)

    print(f"\n📊 抓取总结：")
    print(f"   - 总评论数：{total_comments}")
    print(f"   - UP主评论数：{len(unique_comments)}")
    return unique_comments, up_ids

# ------------------------------
# 4. 推送新增评论
# ------------------------------
def send_new(new_comments):
    if not new_comments:
        print("ℹ️ 无新增评论")
        return

    print(f"\n🚀 新增评论 {len(new_comments)} 条，推送微信")
    content = "\n\n".join([f"【{c['time']}】{c['text']}" for c in new_comments])
    try:
        requests.post(
            f"https://sctapi.ftqq.com/{SENDKEY}.send",
            data={"title": f"UP新评论 {len(new_comments)} 条", "desp": content},
            timeout=10
        )
        print("✅ 推送成功")
    except:
        print("❌ 推送失败")

# ------------------------------
# 主逻辑
# ------------------------------
if __name__ == "__main__":
    print("=== 5分钟自动监控运行 ===")
    print(f"配置：UP_MID={UP_MID}，BV={BV_ID}，Cookie={bool(BILI_COOKIE)}")

    # 1. 基础校验
    if not UP_MID or not UP_MID.isdigit():
        print("❌ UP_MID必须是纯数字！")
        exit()
    if not BV_ID or not BV_ID.startswith("BV"):
        print("❌ BV_ID必须以BV开头！")
        exit()

    # 2. BV转aid
    aid = bv_to_aid(BV_ID)
    if not aid:
        print("❌ BV转换失败！")
        exit()
    print(f"✅ BV转换成功，aid={aid}")

    # 3. 加载历史
    last_ids = load_last()
    print(f"ℹ️ 历史已推送ID数：{len(last_ids)}")

    # 4. 抓取评论
    current_comments, current_ids = get_up_comments(aid)

    # 5. 筛选新增
    new_comments = [c for c in current_comments if c["id"] not in last_ids]

    # 6. 推送
    send_new(new_comments)

    # 7. 保存
    save_current(current_ids)
    print("=== 监控结束 ===\n")
