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
def get_up_comments(aid, up_mid):
    up_mid = int(up_mid)
    comments = []
    # 只抓前5页，足够覆盖新视频
    for page in range(1, 6):
        try:
            # 纯时间排序接口
            url = f"https://api.bilibili.com/x/v2/reply/main?mode=2&oid={aid}&type=1&ps=50&pn={page}"
            res = requests.get(url, headers=HEADERS, timeout=10)
            data = res.json()
            replies = data.get("data", {}).get("replies", [])
            # 强制转列表，杜绝None
            if not isinstance(replies, list):
                replies = []
            
            for r in replies:
                # 顶层评论
                if r.get("mid") == up_mid:
                    ctime = datetime.fromtimestamp(r["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                    comments.append(f"【顶层】{ctime}：{r['content']['message']}")
                
                # 楼中楼（核心修复：强制转列表）
                subs = r.get("replies", [])
                if not isinstance(subs, list):
                    subs = []
                for sub in subs:
                    if sub.get("mid") == up_mid:
                        ctime = datetime.fromtimestamp(sub["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                        comments.append(f"【楼中楼】{ctime}：{sub['content']['message']}")
        except:
            continue
    return comments

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
