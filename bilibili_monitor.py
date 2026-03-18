import requests
import os
from datetime import datetime

# ===================== 仅需确保GitHub Secrets配置这3个 =====================
SENDKEY = os.getenv('SENDKEY')    # Server酱的SendKey
UP_MID = os.getenv('UP_MID')      # UP主的数字ID
BV_ID = os.getenv('BV_ID')        # 视频BV号（如BV1JawLzeE85）
# ==========================================================================

# 固定请求头（避免B站风控）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Referer": f"https://www.bilibili.com/video/{BV_ID}/" if BV_ID else ""
}

def bv_to_oid(bv_id):
    """BV号转OID（带完整容错）"""
    if not bv_id or not bv_id.startswith("BV"):
        print("❌ BV号格式错误")
        return None
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            print(f"❌ BV转OID失败：{data.get('message')}")
            return None
        oid = data["data"]["aid"]
        print(f"✅ BV={bv_id} → OID={oid}")
        return oid
    except Exception as e:
        print(f"❌ BV转OID异常：{str(e)}")
        return None

def get_up_comments(oid, up_mid):
    """抓取UP主评论（彻底杜绝None迭代）"""
    up_comments = []
    up_mid_int = int(up_mid) if (up_mid and up_mid.isdigit()) else 0
    
    # 只抓前8页，每页50条，足够覆盖所有场景
    for page in range(1, 9):
        try:
            # 纯时间倒序接口（最新评论优先）
            url = f"https://api.bilibili.com/x/v2/reply/main?mode=2&oid={oid}&type=1&ps=50&pn={page}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            # 1. 顶层评论列表：强制转空列表，杜绝None
            root_replies = data.get("data", {}).get("replies", [])
            if not isinstance(root_replies, list):
                root_replies = []
                continue

            for root_reply in root_replies:
                # 跳过非字典格式的异常评论
                if not isinstance(root_reply, dict):
                    continue

                # 抓取UP主顶层评论
                if root_reply.get("mid") == up_mid_int:
                    ctime = datetime.fromtimestamp(root_reply["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                    content = root_reply["content"].get("message", "").strip()
                    up_comments.append({
                        "type": "顶层评论",
                        "time": ctime,
                        "content": content
                    })
                    print(f"✅ 抓到顶层评论：{ctime} | {content[:20]}...")

                # 2. 楼中楼回复：强制转空列表，核心修复None迭代问题
                sub_replies = root_reply.get("replies", [])
                if not isinstance(sub_replies, list):
                    sub_replies = []  # 关键：None直接转空列表
                    continue

                for sub_reply in sub_replies:  # 这里绝对不会再报None迭代错误
                    if not isinstance(sub_reply, dict):
                        continue
                    if sub_reply.get("mid") == up_mid_int:
                        ctime = datetime.fromtimestamp(sub_reply["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                        content = sub_reply["content"].get("message", "").strip()
                        up_comments.append({
                            "type": "楼中楼回复",
                            "time": ctime,
                            "content": content
                        })
                        print(f"✅ 抓到楼中楼回复：{ctime} | {content[:20]}...")

            # 防风控：每页间隔1秒
            import time
            time.sleep(1)

        except Exception as e:
            print(f"⚠️ 抓取第{page}页评论异常：{str(e)}")
            continue

    # 去重（按内容+时间）
    unique_comments = []
    seen = set()
    for c in up_comments:
        key = f"{c['content']}_{c['time']}"
        if key not in seen:
            seen.add(key)
            unique_comments.append(c)
    
    print(f"\n📊 抓取完成：共抓到{len(unique_comments)}条UP主唯一评论")
    return unique_comments

def send_wechat_notify(title, content):
    """发送微信推送（带重试）"""
    if not SENDKEY:
        print("❌ SendKey未配置，无法推送")
        return False
    
    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    data = {
        "title": title,
        "desp": content,
        "channel": 9  # 强制走微信服务号通道
    }

    # 重试2次
    for i in range(3):
        try:
            resp = requests.post(url, data=data, timeout=20)
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                print("✅ 微信推送成功！")
                return True
            else:
                print(f"⚠️ 推送失败（第{i+1}次）：{result.get('message')}")
        except Exception as e:
            print(f"⚠️ 推送异常（第{i+1}次）：{str(e)}")
            import time
            time.sleep(2)
    
    print("❌ 微信推送最终失败")
    return False

def main():
    """主函数：全程无None迭代风险"""
    print("=== 🔔 B站UP主评论监控启动 ===")
    print(f"运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 配置校验
    config_ok = True
    if not SENDKEY:
        print("❌ 配置缺失：SENDKEY为空")
        config_ok = False
    if not (UP_MID and UP_MID.isdigit()):
        print("❌ 配置缺失：UP_MID为空或非数字")
        config_ok = False
    if not (BV_ID and BV_ID.startswith("BV")):
        print("❌ 配置缺失：BV_ID为空或格式错误")
        config_ok = False
    if not config_ok:
        return

    # 2. BV转OID
    oid = bv_to_oid(BV_ID)
    if not oid:
        return

    # 3. 抓取UP主评论
    up_comments = get_up_comments(oid, UP_MID)
    if not up_comments:
        print("ℹ️ 未抓到UP主任何评论")
        send_wechat_notify("⚠️ B站监控提示", f"视频{BV_ID}未抓到UP主{UP_MID}的评论")
        return

    # 4. 构造推送内容
    push_content = f"### UP主 {UP_MID} 评论汇总（共{len(up_comments)}条）\n\n"
    for idx, c in enumerate(up_comments, 1):
        push_content += f"{idx}. **{c['type']}** | {c['time']}\n{c['content']}\n\n"

    # 5. 推送微信
    send_wechat_notify(f"🚨 UP主{UP_MID}有新评论（{len(up_comments)}条）", push_content)
    print("=== 🎯 监控结束 ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"❌ 脚本运行出错：{str(e)}"
        print(error_msg)
        # 出错时推送提醒
        if SENDKEY:
            send_wechat_notify("❌ B站监控脚本异常", error_msg)
