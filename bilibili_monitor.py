import requests
import os
import hashlib
from datetime import datetime, timedelta

# 配置项（区分首次/日常）
SENDKEY = os.getenv('SENDKEY')
UP_MID = os.getenv('UP_MID')
VIDEO_AID = os.getenv('VIDEO_AID')
# 首次运行：抓全量历史评论（IS_FIRST_RUN=True），日常运行改为False
IS_FIRST_RUN = True  
DAILY_MONITOR_HOURS = 24  # 日常监控窗口
FIRST_RUN_MAX_PAGE = 20   # 首次抓取最大页数（覆盖所有历史评论）
DAILY_MAX_PAGE = 8        # 日常抓取页数

# 请求头（必填，模拟浏览器）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Referer": f"https://www.bilibili.com/video/BV{VIDEO_AID}/",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cookie": ""  # 可选：填入B站登录Cookie，提升抓取成功率
}

# 获取单页评论（纯时间倒序+适配新视频）
def get_bilibili_comments(aid, page=1):
    # mode=2：纯发布时间倒序，ps=50：每页50条，适配新视频少评论场景
    url = f"https://api.bilibili.com/x/v2/reply/main?mode=2&oid={aid}&type=1&ps=50&pn={page}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            print(f"第{page}页接口错误: {data.get('message')}")
            return None
        # 打印分页信息，方便排查
        replies = data.get("data", {}).get("replies", [])
        if replies:
            latest = datetime.fromtimestamp(replies[0]["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
            earliest = datetime.fromtimestamp(replies[-1]["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
            print(f"第{page}页 | 最新：{latest} | 最早：{earliest} | 共{len(replies)}条")
        return data
    except Exception as e:
        print(f"获取第{page}页失败: {str(e)}")
        return None

# 获取楼中楼详情（兜底空列表）
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
        print(f"楼中楼详情失败(rpid={root_rpid}): {str(e)}")
        return []

# 生成评论指纹（去重）
def generate_comment_fingerprint(comment):
    content = comment["content"].strip().replace("\n", "").replace(" ", "").replace("\t", "")
    time_str = comment["time"]
    return hashlib.md5(f"{content}_{time_str}".encode('utf-8')).hexdigest()

# 提取UP主评论（区分首次/日常）
def extract_up_comments(all_comments_data, up_mid, is_first_run):
    up_comments = []
    up_mid_int = int(up_mid) if up_mid else 0
    seen_fingerprints = set()
    # 首次运行：不过滤时间，抓所有评论；日常运行：过滤24小时内
    expire_time = datetime.now() - timedelta(hours=DAILY_MONITOR_HOURS) if not is_first_run else datetime(2000, 1, 1)

    if not isinstance(all_comments_data, list):
        return up_comments
    
    for comments_data in all_comments_data:
        if not isinstance(comments_data, dict) or "data" not in comments_data:
            continue
        
        root_replies = comments_data["data"].get("replies", [])
        if not isinstance(root_replies, list):
            root_replies = []
        
        for root_reply in root_replies:
            if not isinstance(root_reply, dict) or "mid" not in root_reply or "content" not in root_reply:
                continue
            
            root_rpid = root_reply.get("rpid")
            root_mid = root_reply.get("mid")
            root_content = root_reply["content"].get("message", "")
            
            # 1. 抓取UP主顶层评论
            if root_mid == up_mid_int:
                try:
                    comment_time = datetime.fromtimestamp(root_reply["ctime"])
                    # 首次运行不过滤时间，日常过滤24小时+取消5分钟同步延迟（适配新视频）
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
                            print(f"抓到UP主评论：{comment_time} | {root_content[:20]}...")
                except Exception as e:
                    print(f"处理顶层评论失败(rpid={root_rpid}): {str(e)}")
                    continue
            
            # 2. 抓取UP主楼中楼回复
            sub_replies = root_reply.get("replies", []) or []
            # 补充楼中楼详情（抓全回复）
            sub_detail = get_sub_reply_detail(root_rpid, VIDEO_AID)
            if isinstance(sub_detail, list):
                sub_replies += sub_detail
            
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
                                print(f"抓到UP主回复：{sub_time} | {sub_reply['content'].get('message', '')[:20]}...")
                    except Exception as e:
                        print(f"处理楼中楼失败: {str(e)}")
                        continue
    
    # 按时间倒序排序
    up_comments.sort(key=lambda x: x["time"], reverse=True)
    # 打印统计信息
    if is_first_run:
        print(f"\n✅ 首次抓取完成：共抓到UP主{len(up_comments)}条历史评论")
    else:
        print(f"\n✅ 日常监控完成：共抓到UP主{len(up_comments)}条近{DAILY_MONITOR_HOURS}小时评论")
    return up_comments

# Server酱推送（带重试）
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
            print(f"推送成功（第{i+1}次）: {response.json().get('message', 'success')}")
            return True
        except Exception as e:
            print(f"推送失败（第{i+1}次）: {str(e)}")
            if i < retry:
                import time
                time.sleep(2)
    
    return False

# 主函数（首次全量+日常增量）
def main():
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 开始运行 ===")
    print(f"模式：{'首次全量抓取' if IS_FIRST_RUN else '日常增量监控'}")
    print(f"UP主：{UP_MID} | 视频OID：{VIDEO_AID}")
    
    # 配置检查
    if not all([SENDKEY, UP_MID, VIDEO_AID]):
        send_to_serverchan("⚠️ 配置错误", "请检查SENDKEY/UP_MID/VIDEO_AID")
        return
    
    # 确定抓取页数
    max_page = FIRST_RUN_MAX_PAGE if IS_FIRST_RUN else DAILY_MAX_PAGE
    print(f"计划抓取页数：{max_page}页（每页50条）")
    
    # 抓取评论数据
    all_comments_data = []
    for page in range(1, max_page + 1):
        print(f"\n抓取第 {page}/{max_page} 页...")
        comments_data = get_bilibili_comments(VIDEO_AID, page)
        if not comments_data:
            print(f"第{page}页无数据，停止抓取")
            break
        all_comments_data.append(comments_data)
        # 新视频防风控：每页间隔1秒
        import time
        time.sleep(1)
    
    # 提取UP主评论
    up_comments = extract_up_comments(all_comments_data, UP_MID, IS_FIRST_RUN)
    if not up_comments:
        print("❌ 未抓到UP主任何评论")
        return
    
    # 构造推送内容
    if IS_FIRST_RUN:
        title = f"🚨 首次抓取完成！UP主{UP_MID}共{len(up_comments)}条历史评论"
        content = f"### UP主 {UP_MID} 视频{VIDEO_AID} 所有历史评论\n\n"
    else:
        title = f"🚨 UP主新评论！{datetime.now().strftime('%H:%M:%S')}（{len(up_comments)}条）"
        content = f"### UP主 {UP_MID} 近{DAILY_MONITOR_HOURS}小时新评论\n\n"
    
    for idx, comment in enumerate(up_comments):
        content += f"#### {idx+1}. **{comment['type']}** | {comment['time']}\n"
        if comment['type'] == "楼中楼回复":
            content += f"**被回复评论**：{comment['root_comment']}\n"
        content += f"**内容**：{comment['content']}\n\n"
    
    # 推送消息
    send_to_serverchan(title, content)
    print("=== 运行结束 ===\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"脚本出错：{str(e)}"
        print(error_msg)
        if SENDKEY:
            send_to_serverchan("❌ 脚本运行出错", error_msg)
