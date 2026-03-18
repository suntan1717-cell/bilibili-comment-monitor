import requests
import os
import json
from datetime import datetime, timedelta, timezone

# ===================== 配置项 =====================
SENDKEY = os.getenv('SENDKEY')
UP_MID = os.getenv('UP_MID')
BV_ID = os.getenv('BV_ID')
BILI_COOKIE = os.getenv('BILI_COOKIE', "")
# 新增：Gist 配置（存历史推送记录）
GIST_ID = os.getenv('GIST_ID')          # 你的 Gist ID
GIST_TOKEN = os.getenv('GIST_TOKEN')    # GitHub Token（有 gist 权限）
GIST_FILENAME = "bili_comment_history.json"
# ==================================================

CST = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": f"https://www.bilibili.com/video/{BV_ID}/",
    "Cookie": BILI_COOKIE,
}

# --- 1. 历史记录读写（Gist）---
def load_history_from_gist():
    """从 Gist 加载已推送评论 ID"""
    if not all([GIST_ID, GIST_TOKEN]):
        print("⚠️ 未配置 GIST，无法加载历史记录")
        return set()
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        resp = requests.get(url, headers={"Authorization": f"token {GIST_TOKEN}"}, timeout=10)
        gist = resp.json()
        content = gist["files"][GIST_FILENAME]["content"]
        history = json.loads(content)
        return set(history)
    except Exception as e:
        print(f"⚠️ 加载历史记录失败：{e}")
        return set()

def save_history_to_gist(history_ids):
    """保存已推送评论 ID 到 Gist"""
    if not all([GIST_ID, GIST_TOKEN]):
        print("⚠️ 未配置 GIST，无法保存历史记录")
        return
    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        data = {
            "files": {
                GIST_FILENAME: {"content": json.dumps(list(history_ids))}
            }
        }
        requests.patch(url, headers={"Authorization": f"token {GIST_TOKEN}"}, json=data, timeout=10)
        print("✅ 历史记录已保存到 Gist")
    except Exception as e:
        print(f"⚠️ 保存历史记录失败：{e}")

# --- 2. BV 转 OID ---
def bv_to_oid(bv_id):
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        return resp.json()["data"]["aid"] if resp.json().get("code") == 0 else None
    except:
        return None

# --- 3. 抓取 UP 主评论（最近1小时）---
def get_up_comments_last_hour(oid, up_mid):
    up_mid_int = int(up_mid) if up_mid.isdigit() else 0
    one_hour_ago = datetime.now(CST) - timedelta(hours=1)
    one_hour_ago_ts = int(one_hour_ago.timestamp())
    comments = []

    for page in range(1, 6):
        try:
            url = f"https://api.bilibili.com/x/v2/reply/main?mode=2&oid={oid}&type=1&ps=50&pn={page}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                print(f"⚠️ 第{page}页接口错误：{data.get('code')}")
                break
            replies = data.get("data", {}).get("replies", [])
            if not replies:
                break
            for r in replies:
                if r.get("ctime", 0) < one_hour_ago_ts:
                    return comments
                if r.get("mid") == up_mid_int:
                    comments.append({
                        "id": str(r.get("rpid")),
                        "time": datetime.fromtimestamp(r["ctime"], CST).strftime("%Y-%m-%d %H:%M:%S"),
                        "content": r["content"]["message"],
                        "type": "顶层评论"
                    })
                subs = r.get("replies", [])
                for sub in subs:
                    if sub.get("ctime", 0) < one_hour_ago_ts:
                        continue
                    if sub.get("mid") == up_mid_int:
                        comments.append({
                            "id": str(sub.get("rpid")),
                            "time": datetime.fromtimestamp(sub["ctime"], CST).strftime("%Y-%m-%d %H:%M:%S"),
                            "content": sub["content"]["message"],
                            "type": "楼中楼回复"
                        })
            import time
            time.sleep(1)
        except:
            continue
    return comments

# --- 4. 微信推送 ---
def send_wechat(comments):
    if not SENDKEY or not comments:
        return False
    title = f"🚨 UP主{UP_MID} 新增评论（{len(comments)}条）"
    content = "### 新评论列表\n\n"
    for i, c in enumerate(comments, 1):
        content += f"{i}. **{c['type']}** | {c['time']}\n{c['content']}\n\n"
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{SENDKEY}.send",
            data={"title": title, "desp": content, "channel": 9},
            timeout=10
        )
        return resp.json().get("code") == 0
    except:
        return False

# --- 5. 主逻辑 ---
def main():
    print(f"=== 启动监控 | {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} ===")
    if not all([SENDKEY, UP_MID, BV_ID]):
        print("❌ 配置不全")
        return

    oid = bv_to_oid(BV_ID)
    if not oid:
        print("❌ BV 转 OID 失败")
        return
    print(f"✅ BV={BV_ID} → OID={oid}")

    # 加载已推送历史
    history_ids = load_history_from_gist()
    print(f"ℹ️ 已推送评论数：{len(history_ids)}")

    # 抓取最近1小时 UP 评论
    current_comments = get_up_comments_last_hour(oid, UP_MID)
    print(f"ℹ️ 最近1小时评论数：{len(current_comments)}")

    # 筛选从未推送过的新评论
    new_comments = [c for c in current_comments if c["id"] not in history_ids]
    print(f"ℹ️ 待推送新评论数：{len(new_comments)}")

    if new_comments:
        print("✅ 发现新评论，开始推送")
        if send_wechat(new_comments):
            print("✅ 推送成功")
            # 更新历史记录
            for c in new_comments:
                history_ids.add(c["id"])
            save_history_to_gist(history_ids)
        else:
            print("❌ 推送失败")
    else:
        print("ℹ️ 无新评论，不推送")
    print("=== 监控结束 ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 脚本出错：{e}")
        if SENDKEY:
            send_wechat([{"type": "脚本异常", "time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"), "content": str(e)}])
