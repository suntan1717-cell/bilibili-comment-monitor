import requests
import os
import hashlib
from datetime import datetime, timedelta

# ===================== 仅需配置这3个 =====================
SENDKEY = os.getenv('SENDKEY')
UP_MID  = os.getenv('UP_MID')
BV_ID   = os.getenv('BV_ID')  # 填BV号，如BV1JawLzeE85
# ==========================================================

# 请求头（模拟浏览器，避免风控）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Referer": f"https://www.bilibili.com/video/{BV_ID}/" if BV_ID else ""
}

# BV号自动转OID（带容错）
def bv_to_oid(bv_id):
    if not bv_id:
        print("❌ BV号为空，转换失败")
        return None
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()  # 抛出HTTP错误
        data = res.json()
        if data.get("code") != 0:
            print(f"❌ BV转OID失败：{data.get('message')}")
            return None
        oid = data["data"]["aid"]
        print(f"✅ BV={bv_id} 自动转为 OID={oid}")
        return oid
    except Exception as e:
        print(f"❌ BV转OID出错：{str(e)}")
        return None

# 获取单页评论（带容错）
def get_comments(aid, page=1):
    if not aid:
        return None
    url = f"https://api.bilibili.com/x/v2/reply/main?mode=2&oid={aid}&type=1&ps=50&pn={page}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        data = res.json()
        return data if data.get("code") == 0 else None
    except Exception as e:
        print(f"❌ 抓取第{page}页评论出错：{str(e)}")
        return None

# 生成评论指纹（去重）
def generate_fingerprint(comment):
    content = comment["content"].strip().replace(" ","").replace("\n","").replace("\t","")
    time_str = comment["time"]
    return hashlib.md5(f"{content}_{time_str}".encode('utf-8')).hexdigest()

# 抓取UP主所有评论（全容错）
def get_all_up_comments(aid, up_mid):
    up_comments = []
    seen_fingerprints = set()
    up_mid_int = int(up_mid) if up_mid.isdigit() else 0

    # 抓取前15页，每页间隔1秒防风控
    for page in range(1, 16):
        print(f"\n🔍 抓取第{page}页评论...")
        data = get_comments(aid, page)
        if not data or "data" not in data:
            print(f"⚠️ 第{page}页无数据，停止抓取")
            break

        # 强制转为列表，避免None
        root_replies = data["data"].get("replies", [])
        if not isinstance(root_replies, list):
            root_replies = []
            continue

        for root_reply in root_replies:
            if not isinstance(root_reply, dict):
                continue

            # 1. 抓取顶层评论（UP主发的）
            if root_reply.get("mid") == up_mid_int:
                try:
                    comment_time = datetime.fromtimestamp(root_reply["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                    comment_item = {
                        "content": root_reply["content"].get("message", ""),
                        "time": comment_time,
                        "type": "顶层评论"
                    }
                    fp = generate_fingerprint(comment_item)
                    if fp not in seen_fingerprints:
                        seen_fingerprints.add(fp)
                        up_comments.append(comment_item)
                        print(f"✅ 抓到UP主顶层评论：{comment_time} | {comment_item['content'][:20]}...")
                except Exception as e:
                    print(f"⚠️ 处理顶层评论失败：{str(e)}")
                    continue

            # 2. 抓取楼中楼回复（强制转为列表，核心修复）
            sub_replies = root_reply.get("replies", [])
            if not isinstance(sub_replies, list):
                sub_replies = []  # 关键：None转为空列表
                continue

            for sub_reply in sub_replies:
                if not isinstance(sub_reply, dict):
                    continue
                if sub_reply.get("mid") == up_mid_int:
                    try:
                        sub_time = datetime.fromtimestamp(sub_reply["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                        sub_item = {
                            "content": sub_reply["content"].get("message", ""),
                            "time": sub_time,
                            "type": "楼中楼回复"
                        }
                        fp = generate_fingerprint(sub_item)
                        if fp not in seen_fingerprints:
                            seen_fingerprints.add(fp)
                            up_comments.append(sub_item)
                            print(f"✅ 抓到UP主楼中楼回复：{sub_time} | {sub_item['content'][:20]}...")
                    except Exception as e:
                        print(f"⚠️ 处理楼中楼回复失败：{str(e)}")
                        continue

        # 防风控：每页间隔1秒
        import time
        time.sleep(1)

    # 按时间倒序排序
    up_comments.sort(key=lambda x: x["time"], reverse=True)
    print(f"\n📊 抓取完成：共抓到UP主{len(up_comments)}条唯一评论")
    return up_comments

# 微信推送（带重试+详细日志）
def send_to_wechat(title, content):
    if not SENDKEY or len(SENDKEY) == 0:
        print("❌ SENDKEY未配置，无法推送")
        return False

    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    data = {
        "title": title,
        "desp": content,
        "channel": 9  # 强制走微信服务号通道
    }

    # 重试2次
    for retry in range(3):
        try:
            response = requests.post(url, data=data, timeout=20)
            response.raise_for_status()
            res_json = response.json()
            if res_json.get("code") == 0:
                print("✅ 微信推送成功！")
                return True
            else:
                print(f"⚠️ 推送失败（第{retry+1}次）：{res_json.get('message')}")
        except Exception as e:
            print(f"⚠️ 推送异常（第{retry+1}次）：{str(e)}")
            import time
            time.sleep(2)

    print("❌ 微信推送最终失败")
    return False

# 主函数（全量验证+容错）
def main():
    print("=== 🔔 B站UP主评论监控启动 ===")
    print(f"运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 验证配置（详细提示）
    config_check = {
        "SENDKEY": len(SENDKEY) > 0,
        "UP_MID": len(UP_MID) > 0 and UP_MID.isdigit(),
        "BV_ID": len(BV_ID) > 0 and BV_ID.startswith("BV")
    }
    print(f"\n⚙️ 配置检查：{config_check}")
    
    if not all(config_check.values()):
        print("❌ 配置不全/错误：")
        if not config_check["SENDKEY"]:
            print("  - SENDKEY为空或未配置")
        if not config_check["UP_MID"]:
            print("  - UP_MID为空或不是数字ID")
        if not config_check["BV_ID"]:
            print("  - BV_ID为空或不是以BV开头")
        return

    # BV转OID
    aid = bv_to_oid(BV_ID)
    if not aid:
        print("❌ BV号转换OID失败，请检查BV号是否正确")
        return

    # 抓取UP主评论
    up_comments = get_all_up_comments(aid, UP_MID)
    if not up_comments:
        print("ℹ️ 未抓到UP主任何评论")
        send_to_wechat("⚠️ B站监控提示", f"未抓到UP主{UP_MID}在视频{BV_ID}下的任何评论")
        return

    # 构造推送内容
    push_content = f"### UP主 {UP_MID} 最新评论（共{len(up_comments)}条）\n\n"
    for idx, comment in enumerate(up_comments[:20], 1):  # 最多显示20条
        push_content += f"#### {idx}. **{comment['type']}** | {comment['time']}\n"
        push_content += f"{comment['content']}\n\n"

    # 推送微信
    send_to_wechat(f"🚨 UP主{UP_MID}有新评论（{len(up_comments)}条）", push_content)
    print("=== 🎯 监控结束 ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"❌ 脚本运行出错：{str(e)}"
        print(error_msg)
        # 出错时推送提醒
        if SENDKEY:
            send_to_wechat("❌ B站监控脚本出错", error_msg)
