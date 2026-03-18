import requests
import os
from datetime import datetime

# 配置（从GitHub Secrets读取）
SENDKEY = os.getenv('SENDKEY')
UP_MID = os.getenv('UP_MID')
BV_ID = os.getenv('BV_ID')

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}

# 1. BV转OID（核心）
def bv2oid(bv):
    try:
        res = requests.get(f"https://api.bilibili.com/x/web-interface/view?bvid={bv}", headers=HEADERS, timeout=10)
        return res.json()["data"]["aid"]
    except:
        return None

# 2. 抓取UP评论（全容错）
def get_all_up_comments(aid, up_mid):
    up_comments = []
    seen_fingerprints = set()
    up_mid_int = int(up_mid) if up_mid.isdigit() else 0

    for page in range(1, 15):
        data = get_comments(aid, page)
        if not data or "data" not in data:
            break
        
        # 修复1：顶层评论列表容错
        root_replies = data["data"].get("replies", [])
        if not isinstance(root_replies, list):
            root_replies = []

        for r in root_replies:
            if not isinstance(r, dict):
                continue

            # 处理顶层评论...（原有逻辑不变）

            # 修复2：楼中楼列表容错（第72行核心修复）
            subs = r.get("replies", [])
            if not isinstance(subs, list):
                subs = []
            for sub in subs:  # 第72行：现在subs是列表，不会报错
                if not isinstance(sub, dict):
                    continue
                if sub.get("mid") == up_mid_int:
                    # 处理楼中楼评论...（原有逻辑不变）
                    pass

    return up_comments

# 3. 微信推送
def push_wechat(title, content):
    if not SENDKEY:
        return
    try:
        requests.post(f"https://sctapi.ftqq.com/{SENDKEY}.send", 
                     data={"title": title, "desp": content}, 
                     timeout=10)
        print("推送成功")
    except:
        print("推送失败")

# 主函数
def main():
    print("=== 启动监控 ===")
    # 配置检查
    if not all([SENDKEY, UP_MID, BV_ID]):
        print("配置不全")
        return
    
    # BV转OID
    aid = bv2oid(BV_ID)
    if not aid:
        print("BV转OID失败")
        return
    print(f"BV={BV_ID} → OID={aid}")
    
    # 抓评论
    comments = get_up_comments(aid, UP_MID)
    if not comments:
        print("无UP评论")
        push_wechat("无UP评论", f"视频{BV_ID}未抓到UP{UP_MID}的评论")
        return
    
    # 构造内容
    content = "### UP主评论列表\n" + "\n".join(comments[:10])
    # 推送
    push_wechat(f"抓到{len(comments)}条UP评论", content)
    print("=== 监控结束 ===")

if __name__ == "__main__":
    main()
