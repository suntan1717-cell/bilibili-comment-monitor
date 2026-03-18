import requests
import os
import random
from datetime import datetime, timedelta, timezone

# ===================== 核心配置 =====================
SENDKEY = os.getenv('SENDKEY')
UP_MID = os.getenv('UP_MID')
BV_ID = os.getenv('BV_ID')
BILI_COOKIE = os.getenv('BILI_COOKIE', "")
# 本地历史文件（Actions里临时保存，优先抓评论）
HISTORY_FILE = "comment_ids.txt"
# ==================================================

# 时区+时间配置
CST = timezone(timedelta(hours=8))
# 检测最近12小时的评论（扩大范围，确保能抓到）
DETECT_HOURS = 12

# 强化请求头（100%模拟真实浏览器）
def get_random_headers():
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36"
    ]
    headers = {
        "User-Agent": random.choice(uas),
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
        "Origin": "https://www.bilibili.com",
        "Connection": "keep-alive"
    }
    # 从Cookie提取csrf，补到请求头
    if BILI_COOKIE:
        for kv in BILI_COOKIE.split(";"):
            if "bili_jct" in kv:
                headers["X-Csrf-Token"] = kv.split("=")[-1].strip()
                break
    return headers

# 加载本地历史评论ID（临时）
def load_local_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return set([line.strip() for line in f if line.strip()])
        return set()
    except:
        return set()

# 保存本地历史评论ID
def save_local_history(ids):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(ids))
    except Exception as e:
        print(f"⚠️ 保存本地历史失败：{e}")

# BV转OID（重试3次）
def bv_to_oid(bv_id):
    for retry in range(3):
        try:
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
            resp = requests.get(url, headers=get_random_headers(), timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0:
                oid = data["data"]["aid"]
                print(f"✅ BV转OID成功：{oid}")
                return oid
            else:
                print(f"⚠️ BV转OID失败（{retry+1}次）：{data.get('message')}")
        except Exception as e:
            print(f"⚠️ BV转OID异常（{retry+1}次）：{e}")
            random_sleep(2, 4)
    return None

# 随机延迟（规避风控）
def random_sleep(min_s=1, max_s=3):
    import time
    sleep_time = random.uniform(min_s, max_s)
    time.sleep(sleep_time)

# 核心：抓取UP主所有评论（扩大范围+强制抓）
def get_all_up_comments(oid, up_mid):
    all_comments = []
    up_mid_int = int(up_mid) if up_mid and up_mid.isdigit() else 0
    # 计算检测起始时间戳（12小时前）
    detect_start_ts = int((datetime.now(CST) - timedelta(hours=DETECT_HOURS)).timestamp())
    print(f"🔍 检测时间范围：{datetime.fromtimestamp(detect_start_ts, CST).strftime('%Y-%m-%d %H:%M:%S')} 至今")

    # 抓前15页（覆盖更多评论）
    for page in range(1, 16):
        random_sleep(1, 3)  # 每页随机延迟，避免风控
        try:
            # 评论接口（用更稳定的v2/reply接口）
            url = f"https://api.bilibili.com/x/v2/reply?oid={oid}&type=1&pn={page}&ps=50&sort=2"
            resp = requests.get(url, headers=get_random_headers(), timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                print(f"⚠️ 第{page}页接口错误：{data.get('code')} → {data.get('message')}")
                # 遇到-352，立即重试（加5秒延迟）
                if data.get("code") == -352:
                    random_sleep(5, 7)
                    continue
                break

            replies = data.get("data", {}).get("replies", [])
            if not replies:
                print(f"ℹ️ 第{page}页无评论，停止抓取")
                break

            # 遍历评论
            for r in replies:
                if not isinstance(r, dict):
                    continue
                # 过滤时间：只抓12小时内的
                comment_ts = r.get("ctime", 0)
                if comment_ts < detect_start_ts:
                    print(f"⏩ 第{page}页已到12小时前评论，停止抓取")
                    return all_comments
                
                # 过滤UP主评论
                if r.get("mid") == up_mid_int:
                    ctime = datetime.fromtimestamp(comment_ts, CST).strftime("%Y-%m-%d %H:%M:%S")
                    comment = {
                        "id": str(r.get("rpid", "")),
                        "time": ctime,
                        "content": r["content"].get("message", "").strip(),
                        "type": "顶层评论"
                    }
                    all_comments.append(comment)
                    print(f"✅ 抓到UP主评论：{ctime} | {comment['content'][:30]}...")

                    # 抓楼中楼
                    subs = r.get("replies", [])
                    if isinstance(subs, list):
                        for sub in subs:
                            sub_ts = sub.get("ctime", 0)
                            if sub_ts < detect_start_ts:
                                continue
                            if sub.get("mid") == up_mid_int:
                                sub_ctime = datetime.fromtimestamp(sub_ts, CST).strftime("%Y-%m-%d %H:%M:%S")
                                sub_comment = {
                                    "id": str(sub.get("rpid", "")),
                                    "time": sub_ctime,
                                    "content": sub["content"].get("message", "").strip(),
                                    "type": "楼中楼回复"
                                }
                                all_comments.append(sub_comment)
                                print(f"✅ 抓到UP主楼中楼：{sub_ctime} | {sub_comment['content'][:30]}...")

        except Exception as e:
            print(f"⚠️ 抓取第{page}页异常：{e}")
            continue

    # 去重（按ID）
    unique_comments = []
    seen_ids = set()
    for c in all_comments:
        if c["id"] and c["id"] not in seen_ids:
            seen_ids.add(c["id"])
            unique_comments.append(c)
    print(f"\n📊 共抓到{len(unique_comments)}条UP主唯一评论")
    return unique_comments

# 微信推送
def send_wechat(comments):
    if not SENDKEY or not comments:
        return False
    title = f"🚨 UP主{UP_MID} 新评论（{len(comments)}条）| {datetime.now(CST).strftime('%H:%M')}"
    content = "### 新评论列表\n\n"
    for i, c in enumerate(comments, 1):
        content += f"{i}. **{c['type']}** | {c['time']}\n{c['content']}\n\n"
    # 推送重试3次
    for retry in range(3):
        try:
            resp = requests.post(
                f"https://sctapi.ftqq.com/{SENDKEY}.send",
                data={"title": title, "desp": content, "channel": 9},
                timeout=20
            )
            resp_json = resp.json()
            if resp_json.get("code") == 0:
                print("✅ 微信推送成功！")
                return True
            else:
                print(f"⚠️ 推送失败（{retry+1}次）：{resp_json.get('message')}")
        except Exception as e:
            print(f"⚠️ 推送异常（{retry+1}次）：{e}")
            random_sleep(2, 3)
    return False

# 主函数
def main():
    print(f"=== 🔔 B站评论监控启动 | {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    # 1. 配置校验
    if not all([SENDKEY, UP_MID, BV_ID]):
        print("❌ 配置缺失：SENDKEY/UP_MID/BV_ID必须填")
        return
    if not BILI_COOKIE:
        print("⚠️ 未配置B站Cookie，大概率抓不到评论！")

    # 2. BV转OID
    oid = bv_to_oid(BV_ID)
    if not oid:
        print("❌ BV转OID失败，停止运行")
        return

    # 3. 加载本地历史记录
    history_ids = load_local_history()
    print(f"ℹ️ 已推送过的评论数：{len(history_ids)}")

    # 4. 抓取所有UP主评论（12小时内）
    all_comments = get_all_up_comments(oid, UP_MID)

    # 5. 筛选新增评论（从未推送过）
    new_comments = [c for c in all_comments if c["id"] not in history_ids]
    print(f"ℹ️ 本次新增评论数：{len(new_comments)}")

    # 6. 推送+更新历史
    if new_comments:
        print("\n🚀 检测到新增评论，开始推送")
        if send_wechat(new_comments):
            # 更新历史记录（新增的ID）
            for c in new_comments:
                history_ids.add(c["id"])
            save_local_history(history_ids)
    else:
        print("\nℹ️ 无新增评论，不推送")

    print("=== 🎯 监控结束 ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"❌ 脚本运行出错：{str(e)}"
        print(error_msg)
        # 出错推送
        if SENDKEY:
            send_wechat([{
                "id": "error",
                "time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
                "content": error_msg,
                "type": "脚本异常"
            }])
