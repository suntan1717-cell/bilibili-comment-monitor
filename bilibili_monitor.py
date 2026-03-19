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
BILI_COOKIE = os.getenv("BILI_COOKIE", "")  # 加回Cookie配置

LAST_FILE = "last_comments.json"
CST       = timezone(timedelta(hours=8))
# =================================================

# 强化请求头（含Cookie + 模拟登录用户）
def get_headers():
    # 从Cookie提取csrf
    csrf = ""
    if BILI_COOKIE:
        for kv in BILI_COOKIE.split(";"):
            if "bili_jct" in kv:
                csrf = kv.split("=")[-1].strip()
                break

    headers = {
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36"
        ]),
        "Referer": f"https://www.bilibili.com/video/{BV_ID}/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
        "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Cookie": BILI_COOKIE,
        "X-Csrf-Token": csrf,  # 关键：添加csrf
        "Origin": "https://www.bilibili.com",
        "Connection": "keep-alive"
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
    except Exception as e:
        print(f"⚠️ 加载上次记录失败：{e}")
    return set()

def save_current(ids):
    try:
        with open(LAST_FILE, "w", encoding="utf-8") as f:
            json.dump(list(ids), f, ensure_ascii=False)
        print(f"✅ 保存本次评论ID数：{len(ids)}")
    except Exception as e:
        print(f"⚠️ 保存本次记录失败：{e}")

# ------------------------------
# 2. BV 转 aid（带重试）
# ------------------------------
def bv_to_aid(bv):
    print(f"🔍 正在转换 BV={bv} → aid...")
    for retry in range(2):
        try:
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv}"
            resp = requests.get(url, headers=get_headers(), timeout=15)
            resp.encoding = "utf-8"
            data = resp.json()
            if data.get("code") == 0:
                aid = data["data"]["aid"]
                print(f"✅ BV转换成功：aid={aid}")
                return aid
            else:
                print(f"❌ BV转换失败（重试{retry+1}）：{data.get('message')}（错误码{data.get('code')}）")
        except Exception as e:
            print(f"❌ BV转换异常（重试{retry+1}）：{e}")
            time.sleep(random.uniform(1, 3))
    return None

# ------------------------------
# 3. 抓取评论（针对-352重试）
# ------------------------------
def get_all_comments(aid):
    target_mid = int(UP_MID) if UP_MID.isdigit() else 0
    print(f"🔍 开始抓取 aid={aid} 的评论，目标UP主ID={target_mid}")
    
    all_comments = []
    up_comments = []
    up_comment_ids = set()

    # 抓前8页，每页重试+延迟
    for page in range(1, 9):
        # 随机延迟2-5秒，规避-352
        delay = random.uniform(2, 5)
        print(f"ℹ️ 第{page}页：等待{delay:.1f}秒后抓取...")
        time.sleep(delay)

        for retry in range(3):  # 每页重试3次
            try:
                url = f"https://api.bilibili.com/x/v2/reply/main?mode=3&oid={aid}&type=1&pn={page}&ps=50"
                resp = requests.get(url, headers=get_headers(), timeout=15)
                resp.encoding = "utf-8"
                data = resp.json()

                # 处理-352错误
                if data.get("code") == -352:
                    print(f"⚠️ 第{page}页（重试{retry+1}）：-352风控，延迟5秒重试...")
                    time.sleep(5)
                    continue

                if data.get("code") != 0:
                    print(f"⚠️ 第{page}页接口错误：{data.get('message')}（错误码{data.get('code')}）")
                    break

                replies = data.get("data", {}).get("replies", [])
                if not replies:
                    print(f"ℹ️ 第{page}页无评论，停止抓取")
                    return up_comments, up_comment_ids

                print(f"ℹ️ 第{page}页抓到 {len(replies)} 条评论")
                all_comments.extend(replies)

                # 筛选UP主评论
                for r in replies:
                    r_mid = r.get("mid", 0)
                    rpid = str(r.get("rpid", ""))
                    if r_mid == target_mid and rpid:
                        ctime = datetime.fromtimestamp(r["ctime"], CST).strftime("%m-%d %H:%M")
                        content = r["content"].get("message", "").strip()
                        up_comments.append({
                            "id": rpid,
                            "time": ctime,
                            "text": content
                        })
                        up_comment_ids.add(rpid)
                        print(f"✅ 抓到UP主评论：[{ctime}] {content[:20]}...")

                    # 楼中楼
                    for sub in r.get("replies", []):
                        sub_mid = sub.get("mid", 0)
                        sub_rpid = str(sub.get("rpid", ""))
                        if sub_mid == target_mid and sub_rpid:
                            sub_ctime = datetime.fromtimestamp(sub["ctime"], CST).strftime("%m-%d %H:%M")
                            sub_content = sub["content"].get("message", "").strip()
                            up_comments.append({
                                "id": sub_rpid,
                                "time": sub_ctime,
                                "text": sub_content
                            })
                            up_comment_ids.add(sub_rpid)
                            print(f"✅ 抓到UP主楼中楼：[{sub_ctime}] {sub_content[:20]}...")
                break  # 重试成功，进入下一页
            except Exception as e:
                print(f"⚠️ 第{page}页（重试{retry+1}）抓取异常：{e}")
                if retry == 2:
                    print(f"❌ 第{page}页抓取失败，跳过")

    # 去重
    unique_up_comments = []
    seen_ids = set()
    for c in up_comments:
        if c["id"] not in seen_ids:
            seen_ids.add(c["id"])
            unique_up_comments.append(c)

    print(f"\n📊 抓取总结：")
    print(f"   - 总共抓到评论数：{len(all_comments)}")
    print(f"   - UP主评论数（去重后）：{len(unique_up_comments)}")
    return unique_up_comments, up_comment_ids

# ------------------------------
# 4. 推送新增评论
# ------------------------------
def send_new_comments(new_comments):
    if not new_comments:
        print("ℹ️ 无新增评论")
        return

    print(f"\n🚀 检测到 {len(new_comments)} 条新增评论，准备推送")
    content = ""
    for idx, c in enumerate(new_comments, 1):
        content += f"{idx}. 【{c['time']}】{c['text']}\n\n"

    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{SENDKEY}.send",
            data={
                "title": f"🆕 UP主新增评论 {len(new_comments)} 条",
                "desp": content,
                "channel": 9
            },
            timeout=10
        )
        resp_json = resp.json()
        if resp_json.get("code") == 0:
            print("✅ 微信推送成功！")
        else:
            print(f"❌ 推送失败：{resp_json.get('message')}")
    except Exception as e:
        print(f"❌ 推送异常：{e}")

# ------------------------------
# 主逻辑
# ------------------------------
if __name__ == "__main__":
    print("=== 5分钟自动监控运行 ===")
    print(f"📌 配置检查：UP_MID={UP_MID}，BV_ID={BV_ID}，Cookie配置：{bool(BILI_COOKIE)}")

    # 1. 校验配置
    if not UP_MID or not UP_MID.isdigit():
        print("❌ 错误：UP_MID必须是纯数字")
        exit()
    if not BV_ID or not BV_ID.startswith("BV"):
        print("❌ 错误：BV_ID必须以BV开头")
        exit()
    if not BILI_COOKIE:
        print("⚠️ 警告：未配置BILI_COOKIE，大概率会触发-352风控！")

    # 2. BV转aid
    aid = bv_to_aid(BV_ID)
    if not aid:
        print("❌ BV转换失败，停止运行")
        exit()

    # 3. 加载上次评论ID
    last_ids = load_last()
    print(f"ℹ️ 上次已推送的评论ID数：{len(last_ids)}")

    # 4. 抓取当前评论
    current_up_comments, current_ids = get_all_comments(aid)

    # 5. 筛选新增评论
    new_comments = [c for c in current_up_comments if c["id"] not in last_ids]

    # 6. 推送新增
    send_new_comments(new_comments)

    # 7. 保存本次评论ID
    save_current(current_ids)

    print("=== 监控结束 ===\n")
