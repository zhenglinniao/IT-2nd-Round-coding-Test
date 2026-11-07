export async function getJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(45_000);
  let response: Response;
  try {
    response = await fetch(url, { signal: AbortSignal.any([signal, timeout]) });
  } catch (error) {
    if (signal.aborted) throw error;
    if (timeout.aborted) throw new Error('请求超时，请稍后重试。');
    throw new Error('无法连接服务器，请检查网络后重试。');
  }
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）。`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') message = body.detail;
      else if (body.detail?.problems) message = body.detail.problems.join(' · ');
    } catch {
      /* Retain a safe error for a proxy or HTML error response. */
    }
    throw new Error(message);
  }
  try {
    return await response.json();
  } catch {
    throw new Error('服务器返回的数据格式无效，请稍后重试。');
  }
}

// Only presentation uses Number; all financial arithmetic stays on the server.
export const currency = (value: string | null | undefined) =>
  value == null
    ? '—'
    : (Number(value) < 0 ? '-A$' : 'A$') +
      new Intl.NumberFormat('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
        Math.abs(Number(value)),
      );
export function dateLabel(value: string | null) {
  if (!value) return '未提供日期';
  return new Intl.DateTimeFormat('zh-CN', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    timeZone: 'Australia/Sydney',
  }).format(new Date(value.length === 10 ? value + 'T12:00:00Z' : value));
}
export function timeLabel(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return '未提供';
  return new Intl.DateTimeFormat('zh-CN', {
    day: '2-digit',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
    year: 'numeric',
    timeZone: 'Australia/Sydney',
    timeZoneName: 'short',
    hour12: false,
  }).format(new Date(value));
}
