name: B站UP主评论监控

on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch:

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - name: 拉取代码
        uses: actions/checkout@v4
      
      - name: 设置Python环境
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: 安装依赖
        run: |
          pip install requests
      
      - name: 运行监控脚本
        env:
          SENDKEY: ${{ secrets.SENDKEY }}
          UP_MID: ${{ secrets.UP_MID }}
          BV_ID: ${{ secrets.BV_ID }}
          BILI_COOKIE: ${{ secrets.BILI_COOKIE }}  # 新增Cookie变量
        run: |
          python bilibili_monitor.py
