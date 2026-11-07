import { useEffect, useState } from 'react';
import { currency, dateLabel, getJson, timeLabel } from './api';
import { Icon, ProductPlaceholder } from './icons';
import type { OrderDetail, OrderSummary, Tracking } from './types';
import { courierText } from './localization';

const carrierName = (carrier: string) =>
  ({ startrack: 'StarTrack', auspost: '澳大利亚邮政', tnt: 'TNT 快递' })[carrier] ?? carrier;

function Status({ value }: { value: string }) {
  return (
    <span className={`status ${value === 'Completed' ? 'completed' : ''}`}>
      <span className="status-dot" />
      <span title={value}>{courierText(value)}</span>
    </span>
  );
}

function ErrorPanel({ message, retry }: { message: string; retry: () => void }) {
  return (
    <div className="error-panel" role="alert">
      <Icon name="info" />
      <div>
        <strong>暂时无法加载</strong>
        <p>{message}</p>
        <button className="text-button" onClick={retry}>
          重试 <Icon name="arrow" size={15} />
        </button>
      </div>
    </div>
  );
}

function TrackingPanel({ order }: { order: OrderDetail }) {
  const [results, setResults] = useState<Tracking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setResults([]);
    setError('');
    getJson<{ shipments: Tracking[] }>(
      `/api/orders/${encodeURIComponent(order.id)}/tracking`,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setResults(data.shipments);
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setError(error instanceof Error ? error.message : '物流查询失败，请稍后重试。');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [order.id, refresh]);
  return (
    <section className="panel tracking-section" aria-labelledby="tracking-title">
      <div className="panel-heading">
        <div className="heading-with-icon">
          <Icon name="truck" />
          <h2 id="tracking-title">物流追踪</h2>
          <span className="count-badge">{order.shipments.length}</span>
        </div>
        <button
          className="icon-button"
          aria-label="刷新物流"
          disabled={loading}
          onClick={() => setRefresh((v) => v + 1)}
        >
          <Icon name="refresh" size={17} />
        </button>
      </div>
      <div className="route">
        <div>
          <span className="route-dot" />
          <span>
            Ryde, NSW <strong>{order.shipping.origin_postcode}</strong>
          </span>
        </div>
        <span className="route-path" />
        <Icon name="arrow" size={16} />
        <div>
          <Icon name="pin" size={16} />
          <span>
            {order.customer.address.suburb}, {order.customer.address.state}{' '}
            <strong>{order.customer.address.postcode}</strong>
          </span>
        </div>
      </div>
      {loading && (
        <div className="tracking-loading" role="status">
          <span className="loading-dot" />
          正在查询物流…
        </div>
      )}
      {error && <ErrorPanel message={error} retry={() => setRefresh((v) => v + 1)} />}
      {!loading &&
        !error &&
        results.map((shipment, index) => (
          <article
            className="shipment"
            key={shipment.id}
            aria-label={`${carrierName(shipment.carrier)} ${shipment.tracking_number}`}
          >
            <div className="shipment-heading">
              <div className={`carrier-logo ${shipment.carrier}`}>
                {shipment.carrier === 'tnt' ? 'TNT' : 'ST'}
              </div>
              <div className="shipment-name">
                <h3>{carrierName(shipment.carrier)}</h3>
                <span className="mono tracking-number">{shipment.tracking_number}</span>
              </div>
              <span className="package-index">{String(index + 1).padStart(2, '0')}</span>
            </div>
            <div className="shipment-items">
              此包裹包含 {order.items.filter((item) => item.shipment_id === shipment.id).length}{' '}
              条商品明细
            </div>
            {shipment.query_state === 'available' ? (
              <>
                <div className="tracking-current">
                  <span className="eyebrow">快递状态</span>
                  <strong title={shipment.status || undefined}>
                    {shipment.status ? courierText(shipment.status) : '未提供状态'}
                  </strong>
                  <span>
                    最后更新 · {shipment.last_update_text || timeLabel(shipment.last_update)}
                  </span>
                </div>
                <ol className="timeline">
                  {shipment.events.map((event, i) => (
                    <li key={`${event.date}-${i}`}>
                      <span className="timeline-dot" />
                      <div>
                        <strong title={event.description}>{courierText(event.description)}</strong>
                        <span>{event.location || '未提供地点'}</span>
                        <time>{event.date_text || timeLabel(event.date)}</time>
                      </div>
                    </li>
                  ))}
                </ol>
                {!shipment.events.length && <p className="muted small">暂未提供物流事件。</p>}
              </>
            ) : (
              <div className="tracking-unavailable">
                <Icon name="info" size={18} />
                <div>
                  <strong>
                    {shipment.query_state === 'not_implemented' ? '暂未接入' : '物流暂不可用'}
                  </strong>
                  <p>{shipment.message}</p>
                </div>
              </div>
            )}
            <div className="tracking-meta">
              {shipment.environment === 'testbed' && <span>测试环境</span>}
              {shipment.environment === 'tnt_public' && <span>TNT 官方公开查询</span>}
              {shipment.fetched_at && (
                <span>
                  {shipment.cached ? '缓存查询结果' : '查询时间'} · {timeLabel(shipment.fetched_at)}
                </span>
              )}
            </div>
            {shipment.environment === 'tnt_public' && shipment.query_state === 'available' && (
              <p className="testbed-notice">官网时间格式为日/月/年，未标注时区，按原文显示。</p>
            )}
            {shipment.environment === 'testbed' && shipment.query_state === 'available' && (
              <p className="testbed-notice">
                此为官方测试环境返回的测试轨迹，不代表该订单的实际运输记录。
              </p>
            )}
          </article>
        ))}
      <p className="panel-footnote">物流查询结果缓存 60 秒；订单状态与物流状态分别展示。</p>
    </section>
  );
}

function OrderView({ order }: { order: OrderDetail }) {
  const address = order.customer.address;
  return (
    <>
      <div className="detail-heading">
        <div>
          <div className="eyebrow">订单详情</div>
          <h1>{order.customer.company}</h1>
          <div className="order-meta">
            <span className="mono">{order.id}</span>
            <span className="meta-divider" />
            <span>{dateLabel(order.date)}</span>
          </div>
        </div>
        <Status value={order.status} />
      </div>
      {order.source_note && (
        <div className="source-note">
          <Icon name="info" size={15} />
          {order.source_note}
        </div>
      )}
      {!order.complete && (
        <div className="data-warning" role="alert">
          <Icon name="info" />
          <div>
            <strong>订单金额不完整</strong>
            <p>{order.problems.join(' · ')}。请先修正源数据，再计算订单总额。</p>
          </div>
        </div>
      )}
      <div className="detail-grid">
        <div className="main-column">
          <section className="panel items-section" aria-labelledby="items-title">
            <div className="panel-heading">
              <div className="heading-with-icon">
                <Icon name="box" />
                <h2 id="items-title">商品明细</h2>
              </div>
              <span className="muted small">{order.items.length} 条明细</span>
            </div>
            <div className="table-scroll">
              <table className="items-table">
                <thead>
                  <tr>
                    <th scope="col">商品</th>
                    <th scope="col">数量</th>
                    <th scope="col">
                      建议零售价 <span>含 GST</span>
                    </th>
                    <th scope="col">
                      单价 <span>未含 GST</span>
                    </th>
                    <th scope="col">
                      行小计 <span>未含 GST</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {order.items.map((item, index) => (
                    <tr key={item.id}>
                      <td>
                        <div className="product-cell">
                          <ProductPlaceholder index={index} />
                          <div>
                            <span className="sku mono">{item.sku}</span>
                            <strong>{item.name || '未匹配到商品'}</strong>
                            <span className="product-parcel">
                              包裹 {order.shipments.findIndex((s) => s.id === item.shipment_id) + 1}
                              {!item.matched && ` · ${item.problem}`}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="quantity">{item.quantity}</span>
                      </td>
                      <td>{currency(item.rrp)}</td>
                      <td>{currency(item.unit_ex_gst)}</td>
                      <td className="line-total">{currency(item.subtotal_ex_gst)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="summary-area">
              <div className="summary-caption">
                <span className="eyebrow">金额说明</span>
                <p>
                  建议零售价已含 10% GST。
                  <br />
                  所有金额均以澳元计价。
                </p>
                <span className="placeholder-note">商品图片为占位图。</span>
              </div>
              <dl className="totals">
                {order.totals && order.totals.rounding_adjustment !== '0.00' && (
                  <div className="rounding">
                    <dt>行金额舍入调整</dt>
                    <dd>{currency(order.totals.rounding_adjustment)}</dd>
                  </div>
                )}
                <div>
                  <dt>
                    小计 <span>（未含 GST）</span>
                  </dt>
                  <dd>{currency(order.totals?.subtotal_ex_gst)}</dd>
                </div>
                <div>
                  <dt>
                    商品及服务税 <span>（GST 10%）</span>
                  </dt>
                  <dd>{currency(order.totals?.gst)}</dd>
                </div>
                <div>
                  <dt>
                    运费{' '}
                    {order.shipping.method === 'formula' && (
                      <span className="estimate-tag">估算</span>
                    )}
                  </dt>
                  <dd>{currency(order.shipping.amount)}</dd>
                </div>
                <div className="grand-total">
                  <dt>
                    订单总额 <span>澳元 AUD</span>
                  </dt>
                  <dd>{currency(order.totals?.total)}</dd>
                </div>
              </dl>
            </div>
            <details className="shipping-notes">
              <summary>运费计算与数据来源</summary>
              <p>{order.catalog_note}</p>
              {order.shipping.packages.map((p) => (
                <p key={p.shipment_id}>
                  <strong>
                    {carrierName(
                      order.shipments.find((s) => s.id === p.shipment_id)?.carrier || '',
                    )}{' '}
                    · {currency(p.amount)}
                  </strong>{' '}
                  — {p.note}
                </p>
              ))}
              {!order.shipping.complete && (
                <p>部分或全部包裹暂按 A$0.00 处理，此金额不代表快递公司确认的最终费用。</p>
              )}
              <p>
                金额计算保留完整精度，汇总时再舍入；必要时列出舍入调整，使明细展示金额与汇总一致。
              </p>
            </details>
          </section>
          <section className="panel address-section" aria-labelledby="address-title">
            <div className="panel-heading">
              <div className="heading-with-icon">
                <Icon name="pin" />
                <h2 id="address-title">收货信息</h2>
              </div>
              <span className="small muted">澳大利亚</span>
            </div>
            <div className="address-grid">
              <div>
                <span className="eyebrow">收件人</span>
                <strong>{order.customer.name}</strong>
                <span>{order.customer.company}</span>
                <address>
                  {address.line1}
                  <br />
                  {address.suburb} {address.state} {address.postcode}
                  <br />
                  澳大利亚
                </address>
              </div>
              <div>
                <span className="eyebrow">联系方式</span>
                <span className="contact-label">电话</span>
                <span>{order.customer.phone || '未提供'}</span>
                <span className="contact-label">电子邮箱</span>
                <span className="email">{order.customer.email || '未提供'}</span>
              </div>
            </div>
          </section>
        </div>
        <aside className="tracking-column">
          <TrackingPanel key={order.id} order={order} />
        </aside>
      </div>
      <footer>
        <span>
          订单工作台 <span className="footer-dot">·</span> 澳大利亚业务
        </span>
        <span>
          根据源数据计算 <Icon name="check" size={13} />
        </span>
      </footer>
    </>
  );
}

export default function App() {
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState('');
  const [selected, setSelected] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get('order'),
  );
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [detailError, setDetailError] = useState('');
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [query, setQuery] = useState('');
  const [listRetry, setListRetry] = useState(0);
  const [detailRetry, setDetailRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingList(true);
    setListError('');
    getJson<{ orders: OrderSummary[] }>('/api/orders', controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setOrders(data.orders);
        setSelected((value) => value || data.orders[0]?.id || null);
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setListError(error instanceof Error ? error.message : '订单列表加载失败，请重试。');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingList(false);
      });
    return () => controller.abort();
  }, [listRetry]);

  useEffect(() => {
    if (!selected || listError) return;
    const controller = new AbortController();
    setDetail(null);
    setDetailError('');
    setLoadingDetail(true);
    const params = new URLSearchParams(window.location.search);
    params.set('order', selected);
    window.history.replaceState(null, '', '?' + params.toString());
    getJson<OrderDetail>(`/api/orders/${encodeURIComponent(selected)}`, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setDetail(data);
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setDetailError(error instanceof Error ? error.message : '订单详情加载失败，请重试。');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingDetail(false);
      });
    return () => controller.abort();
  }, [selected, detailRetry, listError]);

  const filtered = orders.filter((order) =>
    `${order.id} ${order.company} ${order.customer_name}`
      .toLowerCase()
      .includes(query.toLowerCase().trim()),
  );
  return (
    <div className="app-shell">
      <a href="#order-content" className="skip-link">
        跳转到订单详情
      </a>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="leaf" size={22} />
          </span>
          <span>
            aeris
            <span className="brand-divider" /> <span className="brand-product">订单工作台</span>
          </span>
        </div>
        <div className="topbar-right">
          <span className="workspace-label">澳大利亚业务</span>
          <span className="region">
            澳洲 <span className="region-dot" />
          </span>
        </div>
      </header>
      <div className="workspace">
        <aside className="sidebar" aria-label="订单">
          <div className="sidebar-title">
            <span className="eyebrow">工作台</span>
            <h2>
              订单 <span>{orders.length}</span>
            </h2>
            <p>查看订单、金额和物流信息</p>
          </div>
          <label className="search-box">
            <Icon name="search" size={17} />
            <span className="sr-only">搜索订单</span>
            <input
              placeholder="搜索订单…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="list-label">{query ? `${filtered.length} 条结果` : '全部订单'}</div>
          {loadingList && (
            <p className="sidebar-state" role="status">
              正在加载订单…
            </p>
          )}
          {!loadingList && !listError && !orders.length && (
            <p className="sidebar-state">暂无订单。</p>
          )}
          {!loadingList && !!orders.length && !filtered.length && (
            <p className="sidebar-state">没有匹配的订单。</p>
          )}
          <nav className="order-list" aria-label="选择订单">
            {filtered.map((order) => (
              <button
                key={order.id}
                className={`order-card ${selected === order.id ? 'selected' : ''}`}
                aria-current={selected === order.id ? 'true' : undefined}
                onClick={() => setSelected(order.id)}
              >
                <div className="card-top">
                  <span className="order-symbol">
                    <Icon name="box" size={18} />
                  </span>
                  <span className={`mini-status ${order.status === 'Completed' ? 'done' : ''}`}>
                    <span title={order.status}>{courierText(order.status)}</span>
                  </span>
                </div>
                <strong>{order.company}</strong>
                <span className="card-order mono">{order.id}</span>
                <div className="card-bottom">
                  <span>{dateLabel(order.date)}</span>
                  <span>{order.item_count} 条明细</span>
                </div>
                <div className="card-amount">
                  <span>{order.complete ? '订单总额' : '数据不完整'}</span>
                  <strong>{currency(order.total)}</strong>
                </div>
              </button>
            ))}
          </nav>
          <div className="sidebar-note">
            <Icon name="info" size={17} />
            <span>
              金额单位为澳元。
              <br />
              物流更新可能存在延迟。
            </span>
          </div>
        </aside>
        <main id="order-content" tabIndex={-1}>
          <div className="breadcrumb">
            工作台 <span>/</span> 订单 <span>/</span>{' '}
            <strong>{selected ? '订单详情' : '概览'}</strong>
          </div>
          {listError ? (
            <ErrorPanel message={listError} retry={() => setListRetry((v) => v + 1)} />
          ) : loadingList || loadingDetail ? (
            <div className="page-loading" role="status">
              <span className="loading-dot" />
              正在加载订单详情…
            </div>
          ) : detailError ? (
            <ErrorPanel message={detailError} retry={() => setDetailRetry((v) => v + 1)} />
          ) : detail ? (
            <OrderView order={detail} />
          ) : (
            <div className="empty-state">
              <Icon name="box" size={40} />
              <h1>订单工作台</h1>
              <p>选择一张订单，查看商品明细、金额汇总和物流信息。</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
