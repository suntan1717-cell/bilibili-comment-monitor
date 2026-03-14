import requests
import os
from datetime import datetime

# 读取配置
SENDKEY = os.getenv('SENDKEY')
UP_MID = os.getenv('UP_MID')
VIDEO_AID = os.getenv('VIDEO_AID')

# 强制推送测试消息（不管有没有评论都推）
def force_push_test():
    # 1. 先打印配置，确认参数传进来了
    print("=== 配置信息 ===")
    print(f"SENDKEY: {SENDKEY[:6]}****" if SENDKEY else "SENDKEY为空！")
    print(f"UP_MID: {UP_MID}")
    print(f"VIDEO_AID: {VIDEO_AID}")
    
    # 2. 调用B站接口，打印原始数据
    print("\n=== B站接口返回 ===")
    url = f"https://api.bilibili.com/x/v2/reply/main?mode=3&oid={VIDEO_AID}&type=1&ps=20&pn=1"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"接口状态码: {resp.status_code}")
        print(f"接口返回内容: {resp.text[:500]}")  # 只打印前500字
    except Exception as e:
        print(f"接口调用失败: {str(e)}")
    
    # 3. 强制推送微信提醒
    print("\n=== 推送微信 ===")
    if not SENDKEY:
        print("SENDKEY为空，推送失败！")
        return
    
    push_url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    push_data = {
        "title": "【测试】GitHub脚本运行了！",
        "desp": f"""
配置检查：
- SENDKEY: {"正常" if SENDKEY else "为空"}
- UP_MID: {UP_MID}
- VIDEO_AID: {VIDEO_AID}

B站接口状态：{resp.status_code if 'resp' in locals() else '调用失败'}
        """
    }
    
    try:
        push_resp = requests.post(push_url, data=push_data, timeout=10)
        print(f"推送结果: {push_resp.text}")
        print("✅ 推送请求已发送，看微信！")
    except Exception as e:
        print(f"❌ 推送失败: {str(e)}")

if __name__ == "__main__":
    force_push_test()
