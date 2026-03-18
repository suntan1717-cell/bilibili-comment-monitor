import requests
import os
import random
from datetime import datetime, timedelta, timezone

# ===================== 配置项 =====================
SENDKEY = os.getenv('SENDKEY')    # Server酱SendKey
UP_MID = os.getenv('UP_MID')      # UP主数字ID
BV_ID = os.getenv('BV_ID')        # 视频BV号
DETECT_MINUTES = 5                # 检测最近5分钟新评论
# 新增：从Secrets读取B站Cookie（关键！解决-352错误）
BILI_COOKIE = os.getenv('BILI_COOKIE', "")
# ==================================================

# 时区配置
CST = timezone(timedelta(hours=8))

# 请求头（新增Cookie+模拟真实浏览器）
HEADERS = {
    "User-Agent": random.choice([  # 随机UA，规避风控
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36"
    ]),
    "Referer": f"https://www.bilibili.com/video/{BV_ID}/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Cookie": BILI_COOKIE,  # 关键：添加登录Cookie
    "Origin": "https://www.bilibili.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site"
}

def bv_to_oid(bv_id):
    """BV号转OID（带重试+风控延迟）"""
    for retry in range(2):
        try:
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0:
                return data["data"]["aid"]
            else:
                print(f"BV转OID失败：{data.get('message')} (错误码{data.get('code')})")
        except Exception as e:
            print(f"BV转OID重试{retry+1}次失败：{e}")
            # 风控延迟：随机等待1-3秒
            time.sleep(random.uniform(1, 3))
    return None

def get_latest_up_comments(oid, up_mid):
    """抓取5分钟内UP主评论（规避风控）"""
    new_comments = []
    up_mid_int = int(up_mid) if up_mid.isdigit() else 0
    detect_start_ts = int((datetime.now(CST) - timedelta(minutes=DETECT_MINUTES)).timestamp())
    print(f"🔍 检测时间范围：{datetime.fromtimestamp(detect_start_ts, CST).strftime('%Y-%m-%d %H:%M:%S')} 至今")

    # 减少抓取页数+增加随机延迟，规避-352风控
    for page in range(1, 6):
        try:
            # 随机延迟1-2秒，避免高频请求
            import time
            time.sleep(random.uniform(1, 2))
            
            # 评论接口（新增csrf参数，从Cookie提取）
            csrf = ""
            if BILI_COOKIE:
                for kv in BILI_COOKIE.split(";"):
                    if "bili_jct" in kv:
                        csrf = kv.split("=")[-1].strip()
                        break
            url = f"https://api.bilibili.com/x/v2/reply/main?mode=2&oid={oid}&type=1&ps=20&pn={page}&csrf={csrf}"

            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("code") != 0:
                print(f"⚠️ 第{page}页接口错误：{data.get('code')} → {data.get('message')}")
                # 遇到-352错误，直接重试一次（加更长延迟）
                if data.get("code") == -352:
                    time.sleep(5)
                    continue
                break

            replies = data.get("data", {}).get("replies", [])
            if not replies:
                print(f"⚠️ 第{page}页无评论，停止抓取")
                break

            for reply in replies:
                comment_ts = reply.get("ctime", 0)
                if comment_ts < detect_start_ts:
                    print(f"⏩ 第{page}页已到5分钟前评论，停止抓取")
                    return new_comments
                
                if reply.get("mid") == up_mid_int:
                    content = reply["content"].get("message", "").strip()
                    new_comments.append({
                        "id": reply.get("rpid", ""),
                        "time": datetime.fromtimestamp(comment_ts, CST).strftime("%Y-%m-%d %H:%M:%S"),
                        "content": content,
                        "type": "顶层评论"
                    })
                    print(f"✅ 抓到UP主新评论：{new_comments[-1]['time']} | {content[:30]}...")

                    # 抓取楼中楼
                    sub_replies = reply.get("replies", [])
                    for sub in sub_replies:
                        sub_ts = sub.get("ctime", 0)
                        if sub_ts < detect_start_ts:
                            continue
                        if sub.get("mid") == up_mid_int:
                            sub_content = sub["content"].get("message", "").strip()
                            new_comments.append({
                                "id": sub.get("rpid", ""),
                                "time": datetime.fromtimestamp(sub_ts, CST).strftime("%Y-%m-%d %H:%M:%S"),
                                "content": sub_content,
                                "type": "楼中楼回复"
                            })
                            print(f"✅ 抓到UP主楼中楼：{new_comments[-1]['time']} | {sub_content[:30]}...")

        except Exception as e:
            print(f"⚠️ 抓取第{page}页异常：{e}")
            continue

    return new_comments

def send_wechat_notify(comments):
    """推送微信"""
    if not SENDKEY:
        print("❌ SENDKEY未配置")
        return False
    
    title = f"🚨 UP主{UP_MID}新评论 | {datetime.now(CST).strftime('%H:%M')}"
    content = f"### 最近{DETECT_MINUTES}分钟新增评论（共{len(comments)}条）\n\n"
    for idx, c in enumerate(comments, 1):
        content += f"{idx}. **{c['type']}** | {c['time']}\n{c['content']}\n\n"
    
    for retry in range(3):
        try:
            url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
            data = {"title": title, "desp": content, "channel": 9}
            resp = requests.post(url, data=data, timeout=20)
            if resp.json().get("code") == 0:
                print("✅ 微信推送成功！")
                return True
            else:
                print(f"⚠️ 推送失败（{retry+1}次）：{resp.json().get('message')}")
        except Exception as e:
            print(f"⚠️ 推送异常（{retry+1}次）：{e}")
            import time
            time.sleep(2)
    return False

def main():
    print(f"=== 🔔 B站评论监控启动 | {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    # 配置校验
    if not all([SENDKEY, UP_MID, BV_ID]):
        print("❌ 配置缺失：SENDKEY/UP_MID/BV_ID必须填")
        return

    # BV转OID
    oid = bv_to_oid(BV_ID)
    if not oid:
        print("❌ BV转OID失败")
        return
    print(f"✅ BV={BV_ID} → OID={oid}")

    # 抓取新评论
    new_comments = get_latest_up_comments(oid, UP_MID)

    # 推送
    if new_comments:
        print(f"\n📊 共抓到{len(new_comments)}条新评论，推送微信")
        send_wechat_notify(new_comments)
    else:
        print("\nℹ️ 未检测到5分钟内UP主的新评论")

    print("=== 🎯 监控结束 ===")

if __name__ == "__main__":
    import time
    try:
        main()
    except Exception as e:
        error_msg = f"❌ 脚本出错：{str(e)}"
        print(error_msg)
        if SENDKEY:
            send_wechat_notify([{"type": "脚本异常", "time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"), "content": error_msg}])
