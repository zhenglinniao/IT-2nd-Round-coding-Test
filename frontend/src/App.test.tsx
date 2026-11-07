import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';
import type { OrderDetail, Tracking } from './types';
import { currency, dateLabel, timeLabel } from './api';
import { courierText } from './localization';

const detail = (id: string, company: string): OrderDetail => ({
  id,
  date: '2025-12-03',
  status: 'In Transit',
  complete: true,
  problems: [],
  source_note: null,
  customer: {
    name: 'Test Customer',
    company,
    phone: '',
    email: '',
    address: {
      line1: '42 Example Street',
      suburb: 'Melbourne',
      state: 'VIC',
      postcode: '3000',
      country: 'AU',
    },
  },
  items: [
    {
      id: 'line',
      sku: 'TEST',
      name: 'Synthetic test product',
      quantity: 2,
      shipment_id: 'parcel',
      matched: true,
      rrp: '22.00',
      unit_ex_gst: '20.00',
      subtotal_ex_gst: '40.00',
    },
  ],
  shipments: [{ id: 'parcel', carrier: 'startrack', tracking_number: 'TEST123' }],
  totals: {
    subtotal_ex_gst: '40.00',
    rounding_adjustment: '0.00',
    gst: '4.00',
    shipping: '0.00',
    total: '44.00',
  },
  catalog_note: 'Synthetic fixture, no live data.',
  shipping: {
    amount: '0.00',
    method: 'fallback',
    complete: false,
    packages: [],
    origin_postcode: '2111',
    destination_postcode: '3000',
  },
});

const first = detail('ORDER-A', 'First Pharmacy');
const second = detail('ORDER-B', 'Second Pharmacy');
const orders = [first, second].map((o) => ({
  id: o.id,
  date: o.date,
  company: o.customer.company,
  customer_name: o.customer.name,
  status: o.status,
  item_count: 1,
  shipment_count: 1,
  complete: true,
  total: '44.00',
  problems: [],
}));
const unavailable: Tracking = {
  id: 'parcel',
  carrier: 'startrack',
  tracking_number: 'TEST123',
  query_state: 'timeout',
  status: null,
  last_update: null,
  message: '快递查询超时，请稍后重试。',
  environment: 'testbed',
  fetched_at: null,
  cached: false,
  events: [],
};

function mockApi(overrides: Record<string, unknown> = {}) {
  const routes: Record<string, unknown> = {
    '/api/orders': { orders },
    '/api/orders/ORDER-A': first,
    '/api/orders/ORDER-B': second,
    '/api/orders/ORDER-A/tracking': { shipments: [unavailable] },
    '/api/orders/ORDER-B/tracking': { shipments: [unavailable] },
    ...overrides,
  };
  const fn = vi.fn(
    async (url: string) =>
      new Response(JSON.stringify(routes[url] ?? { detail: '未找到订单。' }), {
        status: url in routes ? 200 : 404,
        headers: { 'Content-Type': 'application/json' },
      }),
  );
  vi.stubGlobal('fetch', fn);
  return fn;
}

beforeEach(() => {
  window.history.replaceState(null, '', '/');
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('order workspace', () => {
  it('formats a date-only order correctly during standard time and signed amounts clearly', () => {
    expect(dateLabel('2025-07-01')).toBe('2025年7月01日');
    expect(currency('-0.01')).toBe('-A$0.01');
    expect(dateLabel(null)).toBe('未提供日期');
    expect(timeLabel(null)).toBe('未提供');
    expect(timeLabel('2025-12-03T00:00:00Z')).toContain('11:00');
  });
  it('translates known statuses without losing mixed or unknown source statuses', () => {
    expect(courierText('Completed')).toBe('已完成');
    expect(courierText('Delivered / In Transit')).toBe('已送达 / 运输中');
    expect(courierText('Item processed at sorting facility')).toBe('已在分拣中心处理');
    expect(courierText('Shipping information received by Australia Post')).toBe(
      '澳大利亚邮政已收到发货信息',
    );
    expect(courierText('Unrecognised carrier status')).toBe('Unrecognised carrier status');
  });
  it('loads source totals and lets the user switch orders', async () => {
    mockApi();
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'First Pharmacy' })).toBeTruthy();
    expect(screen.getByText('订单总额', { selector: 'dt' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Second Pharmacy/ }));
    expect(await screen.findByRole('heading', { name: 'Second Pharmacy' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'First Pharmacy' })).toBeNull();
    expect(window.location.search).toContain('ORDER-B');
  });

  it('shows courier failure and recovers when refreshed', async () => {
    const fetchMock = mockApi();
    render(<App />);
    expect(await screen.findByText('物流暂不可用')).toBeTruthy();
    const available: Tracking = {
      ...unavailable,
      query_state: 'available',
      status: 'Delivered',
      last_update: '2025-12-03T10:00:00+11:00',
    };
    fetchMock.mockImplementation(
      async (url: string) =>
        new Response(
          JSON.stringify(url.endsWith('/tracking') ? { shipments: [available] } : { orders }),
        ),
    );
    fireEvent.click(screen.getByRole('button', { name: '刷新物流' }));
    expect(await screen.findByText('已送达')).toBeTruthy();
    expect(
      screen.getByText('此为官方测试环境返回的测试轨迹，不代表该订单的实际运输记录。'),
    ).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'First Pharmacy' })).toBeTruthy();
  });

  it('withholds totals for unmatched products', async () => {
    const incomplete = {
      ...first,
      complete: false,
      totals: null,
      problems: ['TEST: missing SKU'],
      items: [
        {
          ...first.items[0],
          name: null,
          matched: false,
          rrp: null,
          unit_ex_gst: null,
          subtotal_ex_gst: null,
        },
      ],
    };
    mockApi({ '/api/orders/ORDER-A': incomplete });
    render(<App />);
    expect(await screen.findByText('订单金额不完整')).toBeTruthy();
    expect(screen.getByText('未匹配到商品')).toBeTruthy();
    expect(screen.getByText('订单总额', { selector: 'dt' }).parentElement?.textContent).toContain(
      '—',
    );
  });

  it('supports search with an explicit no-results state', async () => {
    mockApi();
    render(<App />);
    await screen.findByRole('heading', { name: 'First Pharmacy' });
    fireEvent.change(screen.getByRole('textbox', { name: '搜索订单' }), {
      target: { value: 'unmatched' },
    });
    expect(screen.getByText('没有匹配的订单。')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'First Pharmacy' })).toBeTruthy();
  });

  it('shows an empty order workspace', async () => {
    mockApi({ '/api/orders': { orders: [] } });
    render(<App />);
    expect(await screen.findByText('暂无订单。')).toBeTruthy();
    expect(screen.getByRole('heading', { name: '订单工作台' })).toBeTruthy();
  });

  it('displays an API error and allows retry', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('Network unavailable'));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    expect(await screen.findByText('无法连接服务器，请检查网络后重试。')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('loads an unknown deep link as an error without showing a different order', async () => {
    window.history.replaceState(null, '', '/?order=UNKNOWN');
    mockApi();
    render(<App />);
    expect(await screen.findByText('未找到订单。')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'First Pharmacy' })).toBeNull();
  });
});
