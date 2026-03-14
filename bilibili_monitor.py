import requests
import os
from datetime import datetime

# 从环境变量读取配置（无需修改）
SENDKEY = os.getenv('SENDKEY')
UP_MID = os.getenv('UP_MID')
VIDEO_AID = os.getenv('VIDEO_AID')

# 获取B站评论数据
def get_bilibili_comments(aid, page=1):
    url = f"https://api.bilibili.com/x/v2/reply/main?mode=3&oid={aid}&type=1&ps=20&pn={page}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"获取评论失败: {str(e)}")
        return None

# 提取UP主的所有评论（顶层+楼中楼）
def extract_up_comments(comments_data, up_mid):
    up_comments = []
    if not comments_data or "data" not in comments_data:
        return up_comments
    
    up_mid_int = int(up_mid)
    replies = comments_data["data"].get("replies", [])
    
    # 遍历顶层评论
    for reply in replies:
        # 顶层评论是UP主发的
        if reply.get("mid") == up_mid_int:
            up_comments.append({
                "rpid": str(reply["rpid"]),
                "content": reply["content"]["message"],
                "time": datetime.fromtimestamp(reply["ctime"]).strftime("%Y-%m-%d %H:%M:%S"),
                "type": "顶层评论"
            })
        # 遍历楼中楼回复
        sub_replies = reply.get("replies", [])
        for sub in sub_replies:
            if sub.get("mid") == up_mid_int:
                up_comments.append({
                    "rpid": str(sub["rpid"]),
                    "content": sub["content"]["message"],
                    "time": datetime.fromtimestamp(sub["ctime"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "楼中楼回复"
                })
    return up_comments

# Server酱推送消息
def send_to_serverchan(title, content):
    if not SENDKEY:
        print("SENDKEY未配置")
        return False
    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    data = {
        "title": title,
        "desp": content
    }
    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        print(f"推送成功: {response.json()}")
        return True
    except Exception as e:
        print(f"推送失败: {str(e)}")
        return False

# 读取已推送的评论ID（去重）
def load_sent_rpids():
    sent_rpids = set()
    if os.path.exists("sent_rpids.txt"):
        with open("sent_rpids.txt", "r", encoding="utf-8") as f:
            sent_rpids = set(f.read().splitlines())
    return sent_rpids

# 保存已推送的评论ID
def save_sent_rpids(sent_rpids):
    with open("sent_rpids.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(sent_rpids))

# 主函数
def main():
    print(f"开始监控UP主 {UP_MID} 在视频 {VIDEO_AID} 的评论...")
    
    # 检查配置
    if not all([SENDKEY, UP_MID, VIDEO_AID]):
        print("配置不全！请检查SENDKEY、UP_MID、VIDEO_AID是否正确设置")
        return
    
    # 获取评论数据
    comments_data = get_bilibili_comments(VIDEO_AID)
    if not comments_data:
        print("未获取到评论数据")
        return
    
    # 提取UP主评论
    up_comments = extract_up_comments(comments_data, UP_MID)
    if not up_comments:
        print("未检测到UP主的任何评论")
        return
    
    # 过滤新评论
    sent_rpids = load_sent_rpids()
    new_comments = [c for c in up_comments if c["rpid"] not in sent_rpids]
    
    if not new_comments:
        print("无新的UP主评论")
        return
    
    # 构造推送内容
    title = f"🚨 B站UP主发新评论了！{datetime.now().strftime('%H:%M:%S')}"
    content = "### UP主最新评论\n"
    for comment in new_comments:
        content += f"- 类型：{comment['type']}\n"
        content += f"- 时间：{comment['time']}\n"
        content += f"- 内容：{comment['content']}\n\n"
    
    # 推送消息
    send_to_serverchan(title, content)
    
    # 更新已推送记录
    for comment in new_comments:
        sent_rpids.add(comment["rpid"])
    save_sent_rpids(sent_rpids)
    print(f"成功推送 {len(new_comments)} 条新评论")

if __name__ == "__main__":
    main()
