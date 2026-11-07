# 数据与外部接口核验

核验日期：2026-11-06（Asia/Shanghai）。

## SKU 查询

- 使用题目 SQL.url 替换链接，通过浏览器成功打开 SQL-like Sheet Query。
- 页面明确表名为 `product_list`。示例 `sku_code` 不是真实字段，用其查询返回零行；实际字段为 `SKU`。
- 改用 `SKU IN (...)` 后返回九行，全部匹配；相关源字段摘录在 `data/sku-source.json`，规范化结果在 `data/products.json`。
- 原始值明确带单位 `g`、`mm`、`mm³`。未猜测单位，转换过程可通过 `backend.import_products` 重现。
- 商品名称与 SKU 后缀不必一致，如 AURPUR10 返回名称包含 15g，使用来源名称，不从编码推断规格。
- 终端 HTTPS 曾连接超时/EOF；浏览器成功，不能据此判断查询网站失效。

## Australia Post / StarTrack

已查阅官方 [Track Items](https://developers.auspost.com.au/apis/shipping-and-tracking/reference/track-items) 与 [FAQ](https://developers.auspost.com.au/content/apis/shipping-and-tracking/info/api-resources/faq.html)，实现 GET `/track?tracking_ids=...`，服务端 Basic Auth 与对应 Account-Number。提供的 StarTrack 账号作为字符串保留前导零。适配 consignment、trackable_items 及嵌套 items 的事件结构。

最初使用原始 `courier_testing_account.pdf` 的凭据，以下为历史失败记录；凭据未复制进文档或代码。

| 运单 | 只读测试结果 |
| --- | --- |
| 2FWZ50008569 | 超时；后续本地页面查询又收到 HTTP 401 |
| 2FWZ50008645 | HTTP 401，接口拒绝授权 |

用户于 2026-11-06 明确授权使用 HTML 补充版中的更新凭据，随后向官方 testbed 进行只读验证，结果如下：

| 运单 | HTTP | 规范化状态 | 事件数 |
| --- | --- | --- | --- |
| 2FWZ50008569 | 200 | Delivered in Full | 6 |
| 2FWZ50008645 | 200 | Delivered in Full | 6 |
| RBXZ50016112 | 200 | Delivered in Full | 6 |
| 2FWZ50020500 | 200 | Delivered in Full | 6 |
| 2FWZ50020498 | 200 | Delivered in Full | 6 |
| 2FWZ50020475 | 200 | Delivered in Full | 6 |

每个结果的 tracking_id 与请求一致。六次返回的事件和最后更新时间相同，最后更新时间均为 2025-02-13T11:49:59+11:00。由此只能确认官方测试环境的认证、请求和响应解析成功，不能把这些数据作为所给订单的实际配送证明。页面已增加明确的测试轨迹说明。

更新凭据仅保存在被 Git 忽略的本地 `.env`，其他配置保留，重启服务后清除旧凭据对应的内存缓存。脱敏验证结果保存在忽略的 `tmp/updated-auspost-check.json`。此前自动审批因缺少对该组凭据的单独授权而拒绝重试；本次是在用户明确授权后执行，没有绕过审批。生产环境未测试。

## TNT AU

账号 PDF 提及 RTT 报价和 Secured Weblinking 追踪，文字提到附带技术文档，但实际文件夹没有对应协议附件或接口代码。没有足够依据把 RTT 的 UAT 账号用于其他地区追踪服务。

研究了官方 [TNT AU 国内追踪页](https://www.tntexpress.com.au/interaction/trackntrace.aspx?navigation=1&respCountry=au&respLang=en)、[TNT Web Services](https://express.tnt.com/expresswebservices-website/app/landing.html) 和官方 ExpressConnect 文档入口。公开 ExpressConnect 协议不能证明与给定 AU Weblinking 账号兼容，未将 AU 凭据发送到未确认兼容的端点，也未将国内运单当成国际运单查询。

2026-11-06 已实现独立 `backend/app/tnt.py` 公开页面适配器：GET 官方表单，POST 只读 Track 操作，读取同站结果，再 POST View Details 并读取 ConsignmentHistory。只允许两个已核验的结果路径，拒绝其他主机、HTTP 和制单接口跳转，不发送任何账号密码，不创建运单或申请通知。

运单 `305506914` 的摘要页提示没有 milestone 数据，但历史页实际返回六条事件，最后一条为 `We've delivered your shipment`，`04/12/2025 13:00`，`Melbourne - Airport`。适配器核对运单号和表头，按历史事件时间倒序，翻译已知状态。摘要页的固定进度标签不用于推断运输状态。收件签名等额外个人信息不进入应用输出或测试夹具。

官网没有标注时区，因此 API 的 `date`、`last_update` 保持 null，通过 `date_text`、`last_update_text` 保留原始日/月/年时间；前端明确说明，避免擅自赋予悉尼或 UTC 偏移。查询结果缓存 60 秒，每分钟最多 10 个查询（与邮政共享本地额度）；每个 TNT 查询最多五个 HTTP 请求，总预算 30 秒，无自动重试。支持 9 位数字国内单号，其他单号明确返回不支持。

这是官方公开页面集成，不是已验证的 Weblinking 账号 API。网站结构变更会返回 `invalid_response`，不伪造轨迹。`TNT_TRACKING_ENABLED=false` 可关闭外部查询。RTT 报价、制单及账户级 API 不在本次追踪接入范围，TNT 运费仍为零。
