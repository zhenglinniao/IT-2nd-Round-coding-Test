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

### 2026-11-07：第一轮门户探索（不能作为专用 API 结论）

- 原 PDF 明确区分 Secured Weblinking 与国内 UAT 两组凭据，并提到另附技术规范；当前原题目录仍只有四个文件，没有配套 Weblinking/RTT 协议。
- 已将两组凭据分别配置到被忽略的 `.env`，通过 `TNT_WEBLINKING_USERNAME/PASSWORD` 与 `TNT_UAT_USERNAME/PASSWORD/ACCOUNT` 在服务端加载；不进入前端、不写入示例值，配置对象 repr 隐藏所有承运商凭据。
- 旧 RTT 地址 `https://www.tntexpress.com.au/Rtt/inputRequest.asp` 及对应 UAT 地址在无凭据 GET 核验中均返回 HTTP 404。未向这些无效地址 POST 密码，也未向国际 ExpressConnect 发送国内 UAT 凭据。
- 官方追踪页面的登录脚本指向 `/interaction/asps/login.asp`。分别使用对应凭据 POST 后，均 HTTP 302 跳转同站 `/TNTOnline/Login.aspx`，没有认证成功证据。
- 新版门户使用 `txtUserName`、`txtPassword`、`__VIEWSTATE`、`antiforgeryLogin` 和 `btn_login`。生产门户接受完整表单后 HTTP 200，但脚本提示 `Invalid User name or Password`。国内 UAT 先遇连接错误，随后手动诊断连接成功，也返回同一拒绝提示。这证明两组凭据均未通过对应门户认证，不能据此判断专用 Weblinking/RTT 凭据无效。
- 新增独立手动诊断 `python -m backend.tnt_diagnostics --service all`，只允许固定官方门户，令牌与密码放在 POST 请求体，不跟随重定向，不记录原始响应、Cookie 或凭据，无自动重试。自动测试验证主机隔离、令牌、HTTP 200/302 不误报成功、网络异常和脱敏。

该轮尚未找到正确的 RTT 入口。门户拒绝和旧地址 GET 404 不能证明专用 API 不可用。以下深入复核已确认 RTT UAT 可用，替代此前“缺少有效 RTT 地址”的判断。

### 2026-11-07：专用 RTTNet 与追踪可用性复核（最新结论）

**国内 UAT 账号及 RTTNet 样例报价可用；专用 Weblinking 追踪凭据仍未验证。** 本轮读取原始开源客户端的入口线索后，在 TNT 官方主机直接做真实请求，没有使用第三方代理、模拟报价或其他用户的凭据。

| 核验项目 | 方法及结果 | 能证明的范围 |
| --- | --- | --- |
| 当前公开追踪 | 从无缓存的新 httpx 会话运行现有适配器，单号 `305506914`；返回六条事件，最新 `04/12/2025 13:00` 已送达 | 当前官方页面追踪流程可用，无需账号 |
| 旧官方历史页 | GET `https://www.tntexpress.com.au/InterAction/ASPs/CnmHxAS.asp?305506914`，HTTP 200，返回八条事件，最新 `04/12/2025 13:00:41` | 该历史入口也可用，两个页面粒度不同；应用未切换到旧页，也未伪造补齐事件 |
| RTT UAT 正常请求 | POST `https://uat.tntexpress.com.au/rttnet/inputrequest.aspx`，使用附件国内 UAT 三项配置，HTTP 200 / `text/xml`，五个服务和有效 AUD 价格 | 凭据与该专用报价接口匹配，测试报价真实可用 |
| RTT 错误密码对照 | 同一合法请求，仅将密码设为固定故意错误值；HTTP 200，XML `error/code=004` | 服务检查认证；不能把 HTTP 200 直接当成功 |
| RTT 无效地区对照 | 正确凭据，仅将寄件地区改为 `RYDE/2111`；HTTP 200，XML `brokenRule/code=590` | 已经过认证并执行地区/邮编业务校验，错误不是接口宕机 |
| 正式诊断命令复验 | 使用新增 `probe_rtt` 再次发送合法样例，仍返回同样五项报价 | 验证请求已整理为可重复执行代码 |
| Weblinking 专用追踪、RTT 生产环境 | 没有匹配专用追踪协议；仅无凭据 GET 读取过生产 RTTNet 入口，未发送 UAT 密码 | 仍未验证，不能从门户结果推断 |

RTT UAT 使用 `application/x-www-form-urlencoded` POST，字段为 `Username`、`Password`、`Version=2`、`XMLRequest`。XMLRequest 的值先 URL 编码一次，再由表单编码；不使用邮政 Basic Auth，不把密码放入 URL。XML 根为 `enquiry`，命名空间 `http://www.tntexpress.com.au`，操作为 `ratedTransitTimeEnquiry`，没有创建或预订运单操作。

本次样例：寄件 `GLADESVILLE NSW 2111`，收件 `FITZROY VIC 3065`，寄件日期 `2026-11-09`，一件 1 kg / 10×10×10 cm，非危险品，寄件方付费。官方响应为：

| 服务代码 | AUD 报价 |
| --- | ---: |
| EX12 | 32.57 |
| 712 | 61.52 |
| 73 | 35.89 |
| 75 | 15.42 |
| 76 | 18.18 |

这是一组明确的测试参数，不是题目订单实际装箱。题目的 `RYDE/2111` 组合在 RTT 中触发 590，不能静默修正并当作真实寄件地址。报价响应未在本轮确立 GST/附加费口径，也没有按订单选服务；因此不取最低价直接写入订单，原 TNT 零运费回退保留。生产报价未验证。

复现命令：`python -m backend.tnt_diagnostics --service rtt --shipping-date 2026-11-09`。日期需随验证时间更新。加 `--rtt-controls` 会额外执行一次故意错误密码和一次无效地区对照，总计三次；不自动重试、不跟随跳转，只输出规范化结果和固定提示。HTTP 200 中的认证/业务错误、XML 声明攻击、非 AUD/非有限/负数/异常精度价格均不得报告为报价成功。完整离线后端回归为 117 项通过。

原始响应只在被忽略的本地 `tmp/tnt` 中保留脱敏副本；结构化核验摘要位于被忽略的 `output/tnt`。凭据仍只保留在服务端 `.env`，未提交 GitHub，也未暴露到前端。
