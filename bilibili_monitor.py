import requests
import os
from datetime import datetime, timedelta, timezone

# ===================== 配置项 =====================
SENDKEY = os.getenv('SENDKEY')    # Server酱SendKey
UP_MID = os.getenv('UP_MID')      # UP主数字ID（纯数字）
BV_ID = os.getenv('BV_ID')        # 视频BV号（如BV1JawLzeE85）
DETECT_MINUTES = 5                # 检测最近5分钟的新评论
# ==================================================

# 时区配置（B站接口返回的是UTC+8时间）
CST = timezone(timedelta(hours=8))

# 请求头（模拟登录态，提升抓取成功率）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": f"https://www.bilibili.com/video/{BV_ID}/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}

def bv_to_oid(bv_id):
    """BV号转OID（带重试）"""
    for retry in range(2):
        try:
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0:
                return data["data"]["aid"]
            else:
                print(f"BV转OID失败：{data.get('message')}")
        except Exception as e:
            print(f"BV转OID重试{retry+1}次失败：{e}")
    return None

def get_latest_up_comments(oid, up_mid):
    """抓取最近5分钟内UP主发布的评论（精准检测）"""
    new_comments = []
    up_mid_int = int(up_mid) if up_mid.isdigit() else 0
    # 计算5分钟前的时间戳（UTC+8）
    detect_start_time = datetime.now(CST) - timedelta(minutes=DETECT_MINUTES)
    detect_start_ts = int(detect_start_time.timestamp())
    print(f"🔍 检测时间范围：{detect_start_time.strftime('%Y-%m-%d %H:%M:%S')} 至今")

    # 抓前10页（确保覆盖最新评论，每页50条）
    for page in range(1, 11):
        try:
            # mode=2：纯发布时间倒序（最新评论在第一页第一条）
            url = f"https://api.bilibili.com/x/v2/reply/main?mode=2&oid={oid}&type=1&ps=50&pn={page}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("code") != 0:
                print(f"⚠️ 第{page}页接口返回错误：{data.get('message')}")
                break

            replies = data.get("data", {}).get("replies", [])
            if not isinstance(replies, list) or len(replies) == 0:
                print(f"⚠️ 第{page}页无评论，停止抓取")
                break

            # 遍历当前页评论
            for reply in replies:
                if not isinstance(reply, dict):
                    continue
                
                # 评论发布时间戳（UTC+8）
                comment_ts = reply.get("ctime", 0)
                comment_time = datetime.fromtimestamp(comment_ts, CST)
                
                # 1. 跳过5分钟前的评论（核心：只抓最新）
                if comment_ts < detect_start_ts:
                    print(f"⏩ 第{page}页已到5分钟前评论，停止抓取")
                    return new_comments
                
                # 2. 检测是否是UP主的评论
                if reply.get("mid") == up_mid_int:
                    content = reply["content"].get("message", "").strip()
                    comment_info = {
                        "id": reply.get("rpid", ""),
                        "time": comment_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "content": content,
                        "type": "顶层评论"
                    }
                    new_comments.append(comment_info)
                    print(f"✅ 抓到UP主新评论：{comment_info['time']} | {content[:30]}...")

                    # 检查楼中楼回复（UP主的回复也抓）
                    sub_replies = reply.get("replies", [])
                    if isinstance(sub_replies, list):
                        for sub in sub_replies:
                            sub_ts = sub.get("ctime", 0)
                            if sub_ts < detect_start_ts:
                                continue
                            if sub.get("mid") == up_mid_int:
                                sub_content = sub["content"].get("message", "").strip()
                                sub_info = {
                                    "id": sub.get("rpid", ""),
                                    "time": datetime.fromtimestamp(sub_ts, CST).strftime("%Y-%m-%d %H:%M:%S"),
                                    "content": sub_content,
                                    "type": "楼中楼回复"
                                }
                                new_comments.append(sub_info)
                                print(f"✅ 抓到UP主楼中楼回复：{sub_info['time']} | {sub_content[:30]}...")

            # 每页间隔0.5秒，避免风控
            import time
            time.sleep(0.5)

        except Exception as e:
            print(f"⚠️ 抓取第{page}页异常：{e}")
            continue

    return new_comments

def send_wechat_notify(comments):
    """推送新评论到微信"""
    if not SENDKEY:
        print("❌ SENDKEY未配置，无法推送")
        return False
    
    # 构造推送内容
    title = f"🚨 UP主{UP_MID}新评论 | {datetime.now(CST).strftime('%H:%M')}"
    content = f"### 最近{DETECT_MINUTES}分钟新增评论（共{len(comments)}条）\n\n"
    for idx, c in enumerate(comments, 1):
        content += f"{idx}. **{c['type']}** | {c['time']}\n{c['content']}\n\n"
    
    # 推送请求（带重试）
    for retry in range(3):
        try:
            url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
            data = {
                "title": title,
                "desp": content,
                "channel": 9  # 强制微信服务号通道
            }
            resp = requests.post(url, data=data, timeout=20)
            resp.raise_for_status()
            res_json = resp.json()
            if res_json.get("code") == 0:
                print("✅ 微信推送成功！")
                return True
            else:
                print(f"⚠️ 推送失败（第{retry+1}次）：{res_json.get('message')}")
        except Exception as e:
            print(f"⚠️ 推送异常（第{retry+1}次）：{e}")
            import time
            time.sleep(2)
    
    print("❌ 微信推送最终失败")
    return False

def main():
    print(f"=== 🔔 B站评论监控启动 | {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    # 1. 配置校验
    if not SENDKEY:
        print("❌ 错误：SENDKEY未配置")
        return
    if not (UP_MID and UP_MID.isdigit()):
        print("❌ 错误：UP_MID为空或非数字")
        return
    if not (BV_ID and BV_ID.startswith("BV")):
        print("❌ 错误：BV_ID为空或格式错误（需以BV开头）")
        return

    # 2. BV转OID
    oid = bv_to_oid(BV_ID)
    if not oid:
        print("❌ 错误：BV号转换OID失败，请检查BV号是否有效")
        return
    print(f"✅ BV={BV_ID} → OID={oid}")

    # 3. 抓取5分钟内的新评论
    new_comments = get_latest_up_comments(oid, UP_MID)

    # 4. 有新评论则推送
    if new_comments:
        print(f"\n📊 共抓到{len(new_comments)}条UP主新评论，准备推送")
        send_wechat_notify(new_comments)
    else:
        print("\nℹ️ 未检测到5分钟内UP主的新评论")

    print("=== 🎯 监控结束 ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"❌ 脚本运行出错：{str(e)}"
        print(error_msg)
        # 出错时推送提醒
        if SENDKEY:
            send_wechat_notify([{"type": "脚本异常", "time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"), "content": error_msg}])
