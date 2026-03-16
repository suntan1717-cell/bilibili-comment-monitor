import requests
import os
import hashlib
from datetime import datetime, timedelta

# 从环境变量读取配置
SENDKEY = os.getenv('SENDKEY')
UP_MID = os.getenv('UP_MID')
VIDEO_AID = os.getenv('VIDEO_AID')
# 去重有效期：只监控最近24小时的评论（避免重复检测历史评论）
DUPLICATE_EXPIRE_HOURS = 24

# 获取B站评论数据（抓最新评论+翻页）
def get_bilibili_comments(aid, page=1):
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

# 生成评论唯一指纹（内容+时间，避免重复）
def generate_comment_fingerprint(comment):
    # 拼接内容和时间，生成md5指纹
    content = comment["content"].strip().replace("\n", "").replace(" ", "")
    time_str = comment["time"]
    fingerprint = hashlib.md5(f"{content}_{time_str}".encode('utf-8')).hexdigest()
    return fingerprint

# 提取UP主的所有评论（顶层+楼中楼）+ 过滤过期评论
def extract_up_comments(all_comments_data, up_mid):
    up_comments = []
    up_mid_int = int(up_mid)
    # 计算过期时间：只保留最近24小时的评论
    expire_time = datetime.now() - timedelta(hours=DUPLICATE_EXPIRE_HOURS)
    
    for comments_data in all_comments_data:
        if not comments_data or "data" not in comments_data:
            continue
        
        replies = comments_data["data"].get("replies", [])
        print(f"当前页有 {len(replies)} 条评论，开始筛选UP主评论...")
        
        for reply in replies:
            if not reply or "mid" not in reply or "content" not in reply:
                continue
            
            # 筛选UP主的顶层评论
            comment_mid = reply.get("mid")
            if comment_mid == up_mid_int:
                comment_time = datetime.fromtimestamp(reply["ctime"])
                # 过滤过期评论（只保留24小时内的）
                if comment_time < expire_time:
                    continue
                
                comment_content = reply["content"]["message"]
                comment_info = {
                    "rpid": str(reply["rpid"]),
                    "content": comment_content,
                    "time": comment_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "顶层评论",
                    "fingerprint": generate_comment_fingerprint({
                        "content": comment_content,
                        "time": comment_time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                }
                up_comments.append(comment_info)
                print(f"筛选出UP主评论：{comment_info['content'][:20]}...")
            
            # 筛选UP主的楼中楼回复
            sub_replies = reply.get("replies", []) or []
            for sub in sub_replies:
                if not sub or "mid" not in sub or "content" not in sub:
                    continue
                
                sub_mid = sub.get("mid")
                if sub_mid == up_mid_int:
                    sub_time = datetime.fromtimestamp(sub["ctime"])
                    if sub_time < expire_time:
                        continue
                    
                    sub_content = sub["content"]["message"]
                    sub_info = {
                        "rpid": str(sub["rpid"]),
                        "content": sub_content,
                        "time": sub_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "type": "楼中楼回复",
                        "fingerprint": generate_comment_fingerprint({
                            "content": sub_content,
                            "time": sub_time.strftime("%Y-%m-%d %H:%M:%S")
                        })
                    }
                    up_comments.append(sub_info)
                    print(f"筛选出UP主楼中楼回复：{sub_info['content'][:20]}...")
    
    # 去重：根据指纹保留唯一评论
    unique_comments = []
    seen_fingerprints = set()
    for comment in up_comments:
        if comment["fingerprint"] not in seen_fingerprints:
            seen_fingerprints.add(comment["fingerprint"])
            unique_comments.append(comment)
    
    print(f"筛选后UP主评论数（去重）：{len(unique_comments)}")
    return unique_comments

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

# 主函数
def main():
    print(f"开始监控UP主 {UP_MID} 在视频 {VIDEO_AID} 的评论（仅监控最近{DUPLICATE_EXPIRE_HOURS}小时）...")
    
    # 检查配置
    if not all([SENDKEY, UP_MID, VIDEO_AID]):
        print("配置不全！请检查SENDKEY/UP_MID/VIDEO_AID")
        send_to_serverchan("⚠️ B站监控配置错误", "请检查GitHub Secrets参数")
        return
    
    # 抓取前3页最新评论
    all_comments_data = []
    for page in range(1, 4):
        print(f"\n=== 抓取第 {page} 页评论 ===")
        comments_data = get_bilibili_comments(VIDEO_AID, page)
        if comments_data:
            all_comments_data.append(comments_data)
        else:
            print(f"第 {page} 页无数据，停止翻页")
            break
    
    # 提取UP主评论（自动去重+过滤过期）
    up_comments = extract_up_comments(all_comments_data, UP_MID)
    if not up_comments:
        print("未检测到UP主近24小时的新评论")
        return
    
    # 构造推送内容
    title = f"🚨 B站UP主发新评论了！{datetime.now().strftime('%H:%M:%S')}"
    content = "### UP主最新评论（近24小时）\n"
    for idx, comment in enumerate(up_comments):
        content += f"{idx+1}. **{comment['type']}** | {comment['time']}\n"
        content += f"   内容：{comment['content']}\n\n"
    
    # 推送消息（只推送一次，不会重复）
    send_to_serverchan(title, content)
    print(f"✅ 成功推送 {len(up_comments)} 条唯一评论")

if __name__ == "__main__":
    main()
