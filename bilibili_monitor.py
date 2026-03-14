import requests
import os
from datetime import datetime

# 从环境变量读取配置
SENDKEY = os.getenv('SENDKEY')
UP_MID = os.getenv('UP_MID')
VIDEO_AID = os.getenv('VIDEO_AID')

# 获取B站评论数据（优化：抓最新评论+翻页）
def get_bilibili_comments(aid, page=1):
    # mode=1 抓最新评论（原mode=3是热门评论），pn=页码
    url = f"https://api.bilibili.com/x/v2/reply/main?mode=1&oid={aid}&type=1&ps=20&pn={page}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"获取第{page}页评论失败: {str(e)}")
        return None

# 提取UP主的所有评论（顶层+楼中楼）
def extract_up_comments(all_comments_data, up_mid):
    up_comments = []
    up_mid_int = int(up_mid)
    
    # 遍历所有页的评论数据
    for comments_data in all_comments_data:
        if not comments_data or "data" not in comments_data:
            continue
        
        replies = comments_data["data"].get("replies", [])
        print(f"当前页有 {len(replies)} 条评论，开始筛选UP主评论...")
        
        # 遍历顶层评论
        for reply in replies:
            # 打印每条评论的发布者ID（方便排查）
            comment_mid = reply.get("mid")
            comment_content = reply["content"]["message"][:20] + "..." if len(reply["content"]["message"]) > 20 else reply["content"]["message"]
            print(f"评论ID {reply['rpid']} | 发布者ID {comment_mid} | 内容：{comment_content}")
            
            # 顶层评论是UP主发的
            if comment_mid == up_mid_int:
                up_comments.append({
                    "rpid": str(reply["rpid"]),
                    "content": reply["content"]["message"],
                    "time": datetime.fromtimestamp(reply["ctime"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "顶层评论"
                })
            # 遍历楼中楼回复
            sub_replies = reply.get("replies", [])
            for sub in sub_replies:
                sub_mid = sub.get("mid")
                if sub_mid == up_mid_int:
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
    print(f"开始监控UP主 {UP_MID} 在视频 {VIDEO_AID} 的评论（抓最新评论+翻页）...")
    
    # 检查配置
    if not all([SENDKEY, UP_MID, VIDEO_AID]):
        print("配置不全！请检查SENDKEY、UP_MID、VIDEO_AID是否正确设置")
        send_to_serverchan("⚠️ B站监控配置错误", "请检查GitHub Secrets中的SENDKEY/UP_MID/VIDEO_AID是否正确")
        return
    
    # 抓取前3页最新评论（解决只抓第一页的问题）
    all_comments_data = []
    for page in range(1, 4):
        print(f"\n=== 抓取第 {page} 页评论 ===")
        comments_data = get_bilibili_comments(VIDEO_AID, page)
        if comments_data:
            all_comments_data.append(comments_data)
        else:
            print(f"第 {page} 页无数据，停止翻页")
            break
    
    # 提取UP主评论
    up_comments = extract_up_comments(all_comments_data, UP_MID)
    print(f"\n=== 筛选结果 ===")
    print(f"共找到UP主的评论数：{len(up_comments)}")
    if up_comments:
        for idx, comment in enumerate(up_comments):
            print(f"{idx+1}. {comment['type']} | {comment['time']} | {comment['content']}")
    else:
        print("未检测到UP主的任何评论")
        return
    
    # 过滤新评论
    sent_rpids = load_sent_rpids()
    new_comments = [c for c in up_comments if c["rpid"] not in sent_rpids]
    
    print(f"\n=== 新评论检测 ===")
    print(f"已推送过的评论数：{len(sent_rpids)}")
    print(f"新评论数：{len(new_comments)}")
    
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
    print(f"✅ 成功推送 {len(new_comments)} 条新评论")

if __name__ == "__main__":
    main()
