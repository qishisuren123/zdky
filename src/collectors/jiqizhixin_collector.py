"""机器之心采集器 - ❌ 不可用

测试结果（2026-05-09）：
- jiqizhixin.com 所有公开 URL（/articles, /daily, /feed, /rss）均重定向到"数据服务"付费页
- 返回一个推广页面，不提供任何文章内容
- 反爬做得非常彻底，普通 HTTP 请求完全无法获取内容

替代方案：
1. 付费走"机器之心数据服务"（商业 API）
2. 通过 WeRSS/新榜等第三方抓取公众号
3. 放弃该源，用量子位(qbitai)和 Leiphone RSS 替代覆盖中文 AI 媒体

结论：放弃直接抓取，等后续决定是否走付费方案。
"""

def collect_articles(**kwargs):
    print("  [机器之心] ❌ 不可用 - 站点已全面反爬，需走付费数据服务")
    return []
