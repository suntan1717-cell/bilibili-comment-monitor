import requests
import os
import hashlib
from datetime import datetime, timedelta

# ===================== 你只需要关心这里 =====================
SENDKEY = os.getenv('SENDKEY')
UP_MID  = os.getenv('UP_MID')
BV_ID   = os.getenv('BV_ID')  # 这里填 BV 号，比如 BV1JawLzeE85
# ============================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Referer": f"https://www.bilibili.com/video/{BV_ID}/"
}

# BV 自动转 OID（你不用管）
def bv_to_oid(bv_id):
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()
        return data["data"]["aid"]
    except:
        return None

# 获取评论（纯最新时间排序，不会漏）
def get_comments(aid, page=1):
    url = f"https://api.bilibili.com/x/v2/reply/main?mode=2&oid={aid}&type=1&ps=50&pn={page}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        return res.json()
    except:
        return None

# 去重指纹
def fp(comment):
    c = comment["content"].strip().replace(" ","").replace("\n","")
    t = comment["time"]
    return hashlib.md5(f"{c}_{t}".encode()).hexdigest()

# 抓取 UP 所有评论（第一次也能全抓）
def get_all_up_comments(aid, up_mid):
    up_mid = int(up_mid)
    all_found = []
    seen = set()

    for page in range(1, 15):  # 抓15页，足够新视频+历史
        data = get_comments(aid, page)
        if not data or "data" not in data:
            break
        replies = data["data"].get("replies", [])
        if not replies:
            break

        for r in replies:
            # 顶层评论
            if r.get("mid") == up_mid:
                t = datetime.fromtimestamp(r["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                item = {
                    "content": r["content"]["message"],
                    "time": t,
                    "type": "顶层评论"
                }
                f = fp(item)
                if f not in seen:
                    seen.add(f)
                    all_found.append(item)

            # 楼中楼
            subs = r.get("replies", [])
            for sub in subs:
                if sub.get("mid") == up_mid:
                    t = datetime.fromtimestamp(sub["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                    item = {
                        "content": sub["content"]["message"],
                        "time": t,
                        "type": "楼中楼回复"
                    }
                    f = fp(item)
                    if f not in seen:
                        seen.add(f)
                        all_found.append(item)
    return all_found

# 微信推送
def push(title, content):
    if not SENDKEY:
        print("无 SENDKEY")
        return False
    try:
        url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
        data = {"title": title, "desp": content}
        requests.post(url, data=data, timeout=10)
        print("推送完成")
        return True
    except Exception as e:
        print("推送失败", e)
        return False

# 主逻辑
def main():
    print("=== 开始监控 ===")
    if not all([SENDKEY, UP_MID, BV_ID]):
        print("配置不全")
        return

    aid = bv_to_oid(BV_ID)
    if not aid:
        print("BV 转 OID 失败")
        return

    print(f"BV={BV_ID} 自动转为 OID={aid}")
    comments = get_all_up_comments(aid, UP_MID)

    if not comments:
        print("未抓到 UP 评论")
        return

    content = "### UP 主最新评论\n\n"
    for i, c in enumerate(comments[-10:], 1):
        content += f"{i}.【{c['type']}】{c['time']}\n{c['content']}\n\n"

    push(f"UP 主有新评论（共{len(comments)}条）", content)

if __name__ == "__main__":
    main()
