import requests
import os
import json
from datetime import datetime

# ===================== 配置项 =====================
SENDKEY = os.getenv('SENDKEY')    # Server酱SendKey
UP_MID = os.getenv('UP_MID')      # UP主数字ID
BV_ID = os.getenv('BV_ID')        # 视频BV号
HISTORY_FILE = "comment_history.txt"  # 历史评论记录文件
# ==================================================

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Referer": f"https://www.bilibili.com/video/{BV_ID}/" if BV_ID else ""
}

def load_history_comments():
    """加载历史评论记录（用于对比新评论）"""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except:
        return []

def save_history_comments(comments):
    """保存最新评论到历史文件"""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(comments, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 保存历史记录失败：{e}")

def bv_to_oid(bv_id):
    """BV号转OID"""
    if not bv_id or not bv_id.startswith("BV"):
        print("❌ BV号格式错误")
        return None
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        return data["data"]["aid"] if data.get("code") == 0 else None
    except:
        return None

def get_up_comments(oid, up_mid):
    """抓取UP主所有评论"""
    up_comments = []
    up_mid_int = int(up_mid) if (up_mid and up_mid.isdigit()) else 0
    
    for page in range(1, 6):  # 5分钟运行，只抓前5页（更快）
        try:
            url = f"https://api.bilibili.com/x/v2/reply/main?mode=2&oid={oid}&type=1&ps=50&pn={page}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            data = resp.json()
            
            root_replies = data.get("data", {}).get("replies", [])
            if not isinstance(root_replies, list):
                root_replies = []

            for root_reply in root_replies:
                if not isinstance(root_reply, dict):
                    continue

                # 顶层评论
                if root_reply.get("mid") == up_mid_int:
                    ctime = datetime.fromtimestamp(root_reply["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                    content = root_reply["content"].get("message", "").strip()
                    up_comments.append({
                        "id": f"{root_reply.get('rpid')}",  # 唯一标识
                        "type": "顶层评论",
                        "time": ctime,
                        "content": content
                    })

                # 楼中楼
                sub_replies = root_reply.get("replies", [])
                if not isinstance(sub_replies, list):
                    sub_replies = []
                for sub_reply in sub_replies:
                    if not isinstance(sub_reply, dict):
                        continue
                    if sub_reply.get("mid") == up_mid_int:
                        ctime = datetime.fromtimestamp(sub_reply["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                        content = sub_reply["content"].get("message", "").strip()
                        up_comments.append({
                            "id": f"{sub_reply.get('rpid')}",  # 唯一标识
                            "type": "楼中楼回复",
                            "time": ctime,
                            "content": content
                        })
            import time
            time.sleep(0.5)  # 缩短间隔，适配5分钟运行
        except:
            continue

    # 去重（按唯一ID）
    unique_comments = []
    seen_ids = set()
    for c in up_comments:
        if c["id"] not in seen_ids:
            seen_ids.add(c["id"])
            unique_comments.append(c)
    return unique_comments

def get_new_comments(current_comments, history_comments):
    """对比历史，获取新增评论"""
    history_ids = {c["id"] for c in history_comments}
    new_comments = [c for c in current_comments if c["id"] not in history_ids]
    return new_comments

def send_wechat(title, content):
    """发送微信推送"""
    if not SENDKEY:
        return False
    try:
        url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
        data = {"title": title, "desp": content, "channel": 9}
        resp = requests.post(url, data=data, timeout=20)
        return resp.json().get("code") == 0
    except:
        return False

def main():
    print(f"=== 启动监控 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    # 1. 配置校验
    if not all([SENDKEY, UP_MID, BV_ID]):
        print("❌ 配置不全")
        return

    # 2. BV转OID
    oid = bv_to_oid(BV_ID)
    if not oid:
        print("❌ BV转OID失败")
        return

    # 3. 加载历史评论
    history_comments = load_history_comments()
    print(f"ℹ️ 历史评论数：{len(history_comments)}")

    # 4. 抓取当前评论
    current_comments = get_up_comments(oid, UP_MID)
    print(f"ℹ️ 当前评论数：{len(current_comments)}")

    # 5. 对比新增评论
    new_comments = get_new_comments(current_comments, history_comments)
    print(f"ℹ️ 新增评论数：{len(new_comments)}")

    # 6. 仅当有新增评论时推送+保存历史
    if new_comments:
        print("✅ 检测到新评论，准备推送")
        # 构造推送内容
        content = f"### UP主 {UP_MID} 新评论（{len(new_comments)}条）\n\n"
        for idx, c in enumerate(new_comments, 1):
            content += f"{idx}. **{c['type']}** | {c['time']}\n{c['content']}\n\n"
        # 推送微信
        if send_wechat(f"🚨 UP主新评论 | {datetime.now().strftime('%H:%M')}", content):
            print("✅ 微信推送成功")
        else:
            print("❌ 微信推送失败")
        # 保存最新评论到历史文件
        save_history_comments(current_comments)
    else:
        print("ℹ️ 无新增评论，不推送")

    print("=== 监控结束 ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 脚本出错：{e}")
