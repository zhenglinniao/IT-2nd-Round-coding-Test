// Translate known source statuses for display without changing API/source values.
const courierLabels: Record<string, string> = {
  completed: '已完成',
  'in transit': '运输中',
  pending: '待处理',
  processing: '处理中',
  shipped: '已发货',
  delivered: '已送达',
  "we've delivered your shipment": '已送达',
  "your shipment's with a driver": '正在派送',
  "we're processing your shipment": '货件处理中',
  "we've collected your shipment": '已揽收',
  'your shipment data is lodged': '已收到运单信息',
  'delivered in full': '已全部送达',
  'item delivered': '已送达',
  'picked up': '已揽收',
  'on board for delivery': '派送中',
  'onboard for delivery': '派送中',
  'out for delivery': '派送中',
  'awaiting collection': '待领取',
  'shipping information received': '已收到发货信息',
  'shipment information received': '已收到运单信息',
  'shipping information approved by australia post': '澳大利亚邮政已确认发货信息',
  'received by australia post for transportation to processing facility':
    '澳大利亚邮政已收件，准备运往处理中心',
  'processed at facility': '已在处理中心处理',
  'in transit to next facility': '正在运往下一处理中心',
  'item processed at facility': '已在处理中心处理',
  'item processed at sorting facility': '已在分拣中心处理',
  'shipping information received by australia post': '澳大利亚邮政已收到发货信息',
  'freight handling': '货件处理中',
  'tracking event': '物流事件',
  'delivered - left in a safe place': '已送达并放置于安全位置',
  'attempted delivery - no one in attendance': '尝试投递时无人接收',
  cancelled: '已取消',
  canceled: '已取消',
};

export function courierText(value: string): string {
  return value
    .split(' / ')
    .map((part) => courierLabels[part.trim().toLowerCase()] ?? part)
    .join(' / ');
}
