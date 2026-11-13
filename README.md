# 标准库采集器

一个只使用 Python 标准库的小型采集器。它只采集 sitemap 中列出的 URL，
不做全站链接爬取，并严格遵守站点目录中的 robots.txt。

## 运行

```bash
python -m crawl.cli --site demo/site --out out/report.json
```

可选参数：

- --user-agent：参与 robots 分组匹配的 UA，默认 DemoBot/1.0。
- --delay：同一 host 两次请求的最小间隔秒数，默认 0.5。
- --sitemap：站点目录内的入口 sitemap 文件名；未指定时优先读取
  robots.txt 中的 Sitemap，再回退到 sitemap.xml。

demo 使用 file:// URL 直接读取站点目录，因此无需网络。

## robots.txt 语义

- 按连续的 User-agent 字段分组；UA 名称大小写不敏感，精确分组优先于
  User-agent: * 通配分组。
- 规则字段为 Allow 与 Disallow。空 Disallow 表示允许全部，不产生
  禁止规则。
- 每条规则的匹配长度按规则文本长度计算，$ 结尾锚点本身不计入长度。
- 一个路径同时命中多条规则时，最长规则胜出；长度相同则 Allow 胜出。
- * 匹配任意长度的任意字符，$ 表示路径必须在该位置结束。
- 没有任何规则命中时默认允许。

本地 file:// 采集时，URL 会映射为相对于站点目录的文档根路径，例如
demo/site/private/a.html 对应 /private/a.html，因此同一份 robots 规则
对本地夹具与 HTTP 站点的行为一致。

## sitemap 展开与去重

- 支持 sitemapindex 与 urlset 两种根节点，忽略 XML 命名空间差异。
- 解析每个 loc 与 lastmod。
- urlset 中的 URL 先规范化再去重：去掉 fragment、统一 scheme 与 host
  大小写、把相对路径基于当前 sitemap 的 URL 解析为绝对 URL。
- 第一次出现的规范化 URL 参与后续判断；后续重复项进入
  skipped_duplicate。
- 入口 sitemap 记为第 0 层；嵌套 sitemapindex 最多再展开两层，达到
  深度上限后即使仍是 index 也停止展开。
- 已访问的 sitemap 文档不会重复加载；自指 sitemapindex 会直接跳过，不会
  死循环。

## 礼貌延迟

CrawlPolicy 按 host（含显式端口）记录上次请求时间。向同一 host 发起下一次
请求前，若距上次请求不足 --delay 秒则睡眠补齐；不同 host 各自计时，
--delay 0 表示不等待。

## 报告

输出 JSON 包含：

- crawled：成功采集的 URL，每条含 url、status、bytes、title。
- skipped_by_robots：被 robots 禁止、未发起请求的 URL。
- skipped_duplicate：规范化后重复的 URL。
- not_found：发起请求但资源不存在或请求失败的 URL。
- summary：候选 URL 数以及上述各集合的计数。

命令结束时 stdout 固定打印一行摘要，顺序为候选 URL 数、采集数、
robots 拦截数、去重数。

## 测试

```bash
python -m unittest test_crawl -v
```
