import requests
import os
import hashlib
from datetime import datetime, timedelta

# 配置项
SENDKEY = os.getenv('SENDKEY')
UP_MID = os.getenv('UP_MID')
VIDEO_AID = os.getenv('VIDEO_AID')
DUPLICATE_EXPIRE_HOURS = 12
MAX_PAGE = 5
CHECK_SUB_REPLY_DETAIL = True

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Referer": f"https://www.bilibili.com/video/BV{VIDEO_AID}/",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cookie": ""
}

# 获取单页评论
def get_bilibili_comments(aid, page=1):
    url = f"https://api.bilibili.com/x/v2/reply/main?mode=1&oid={aid}&type=1&ps=20&pn={page}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            print(f"接口返回错误: {data.get('message')}")
            return None
        return data
    except Exception as e:
        print(f"获取第{page}页评论失败: {str(e)}")
        return None

# 获取楼中楼详情（确保返回列表）
def get_sub_reply_detail(root_rpid, aid):
    if not root_rpid:
        return []
    url = f"https://api.bilibili.com/x/v2/reply/reply?oid={aid}&type=1&ps=50&pn=1&root={root_rpid}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("replies", []) if data.get("code") == 0 else []
    except Exception as e:
        print(f"获取楼中楼详情失败(rpid={root_rpid}): {str(e)}")
        return []

# 生成评论指纹
def generate_comment_fingerprint(comment):
    content = comment["content"].strip().replace("\n", "").replace(" ", "").replace("\t", "")
    time_str = comment["time"]
    return hashlib.md5(f"{content}_{time_str}".encode('utf-8')).hexdigest()

# 提取UP主评论（全量容错）
def extract_up_comments(all_comments_data, up_mid):
    up_comments = []
    up_mid_int = int(up_mid) if up_mid else 0
    expire_time = datetime.now() - timedelta(hours=DUPLICATE_EXPIRE_HOURS)
    seen_fingerprints = set()

    # 遍历所有页数据（先判断是否为空）
    if not isinstance(all_comments_data, list):
        return up_comments
    
    for comments_data in all_comments_data:
        if not isinstance(comments_data, dict) or "data" not in comments_data:
            continue
        
        # 顶层评论列表（强制转为列表）
        root_replies = comments_data["data"].get("replies", [])
        if not isinstance(root_replies, list):
            root_replies = []
        
        for root_reply in root_replies:
            # 基础字段容错
            if not isinstance(root_reply, dict) or "mid" not in root_reply or "content" not in root_reply:
                continue
            
            root_rpid = root_reply.get("rpid")
            root_mid = root_reply.get("mid")
            root_content = root_reply["content"].get("message", "")
            
            # 1. 顶层评论是UP主发的
            if root_mid == up_mid_int:
                try:
                    comment_time = datetime.fromtimestamp(root_reply["ctime"])
                    if comment_time >= expire_time:
                        comment_info = {
                            "rpid": str(root_rpid),
                            "content": root_content,
                            "time": comment_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "type": "顶层评论",
                            "root_comment": ""
                        }
                        fingerprint = generate_comment_fingerprint(comment_info)
                        if fingerprint not in seen_fingerprints:
                            seen_fingerprints.add(fingerprint)
                            up_comments.append(comment_info)
                except Exception as e:
                    print(f"处理顶层评论失败(rpid={root_rpid}): {str(e)}")
                    continue
            
            # 2. 楼中楼回复（双重容错：强制转为列表）
            sub_replies = root_reply.get("replies", [])
            if not isinstance(sub_replies, list):
                sub_replies = []
            
            # 3. 补充楼中楼详情（确保是列表）
            if CHECK_SUB_REPLY_DETAIL:
                sub_detail = get_sub_reply_detail(root_rpid, VIDEO_AID)
                if isinstance(sub_detail, list):
                    sub_replies += sub_detail
            
            # 遍历楼中楼（先判断是否为列表）
            if not isinstance(sub_replies, list):
                continue
            
            for sub_reply in sub_replies:
                if not isinstance(sub_reply, dict) or "mid" not in sub_reply or "content" not in sub_reply:
                    continue
                
                sub_mid = sub_reply.get("mid")
                if sub_mid == up_mid_int:
                    try:
                        sub_time = datetime.fromtimestamp(sub_reply["ctime"])
                        if sub_time >= expire_time:
                            # 被回复评论内容容错
                            root_content_show = root_content[:30] + "..." if len(root_content) > 30 else root_content
                            comment_info = {
                                "rpid": str(sub_reply.get("rpid")),
                                "content": sub_reply["content"].get("message", ""),
                                "time": sub_time.strftime("%Y-%m-%d %H:%M:%S"),
                                "type": "楼中楼回复",
                                "root_comment": root_content_show
                            }
                            fingerprint = generate_comment_fingerprint(comment_info)
                            if fingerprint not in seen_fingerprints:
                                seen_fingerprints.add(fingerprint)
                                up_comments.append(comment_info)
                    except Exception as e:
                        print(f"处理楼中楼评论失败: {str(e)}")
                        continue
    
    print(f"最终筛选出UP主近{DUPLICATE_EXPIRE_HOURS}小时的唯一评论/回复数：{len(up_comments)}")
    return up_comments

# 推送消息（带重试）
def send_to_serverchan(title, content, retry=2):
    if not SENDKEY:
        print("SENDKEY未配置")
        return False
    
    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    data = {"title": title, "desp": content}
    
    for i in range(retry + 1):
        try:
            response = requests.post(url, data=data, timeout=15)
            response.raise_for_status()
            print(f"推送成功（第{i+1}次尝试）: {response.json().get('message', 'success')}")
            return True
        except Exception as e:
            print(f"推送失败（第{i+1}次尝试）: {str(e)}")
            if i < retry:
                import time
                time.sleep(2)
    
    return False

# 主函数
def main():
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 开始监控 ===")
    print(f"监控UP主：{UP_MID} | 视频：{VIDEO_AID} | 近{DUPLICATE_EXPIRE_HOURS}小时 | 抓取前{MAX_PAGE}页")
    
    # 配置检查
    if not all([SENDKEY, UP_MID, VIDEO_AID]):
        send_to_serverchan("⚠️ B站监控配置错误", "请检查GitHub Secrets中的参数")
        return
    
    # 抓取多页评论
    all_comments_data = []
    for page in range(1, MAX_PAGE + 1):
        print(f"\n抓取第 {page}/{MAX_PAGE} 页评论...")
        comments_data = get_bilibili_comments(VIDEO_AID, page)
        if not comments_data:
            print(f"第{page}页无数据，停止抓取")
            break
        all_comments_data.append(comments_data)
    
    # 提取UP主评论
    up_comments = extract_up_comments(all_comments_data, UP_MID)
    if not up_comments:
        print("未检测到UP主近12小时的新评论/回复")
        return
    
    # 构造推送内容
    title = f"🚨 B站UP主新回复！{datetime.now().strftime('%H:%M:%S')}"
    content = f"### UP主 {UP_MID} 近{DUPLICATE_EXPIRE_HOURS}小时评论/回复\n\n"
    for idx, comment in enumerate(up_comments):
        content += f"#### {idx+1}. {comment['type']} | {comment['time']}\n"
        if comment['type'] == "楼中楼回复":
            content += f"**被回复评论**：{comment['root_comment']}\n"
        content += f"**回复内容**：{comment['content']}\n\n"
    
    # 推送
    send_to_serverchan(title, content)
    print("=== 监控结束 ===\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"脚本运行出错: {str(e)}")
        # 出错时推送提醒
        if SENDKEY:
            send_to_serverchan("❌ B站监控脚本运行出错", f"错误信息：{str(e)}\n时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
