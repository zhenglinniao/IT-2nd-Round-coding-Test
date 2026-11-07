export type OrderSummary = {
  id: string;
  date: string | null;
  status: string;
  company: string;
  customer_name: string;
  item_count: number;
  shipment_count: number;
  complete: boolean;
  total: string | null;
  problems: string[];
};
export type Shipment = { id: string; carrier: string; tracking_number: string };
export type Item = {
  id: string;
  sku: string;
  quantity: number;
  shipment_id: string;
  name: string | null;
  matched: boolean;
  rrp: string | null;
  unit_ex_gst: string | null;
  subtotal_ex_gst: string | null;
  problem?: string;
};
export type Totals = {
  subtotal_ex_gst: string;
  rounding_adjustment: string;
  gst: string;
  shipping: string;
  total: string;
};
export type OrderDetail = {
  id: string;
  date: string;
  status: string;
  source_note: string | null;
  complete: boolean;
  problems: string[];
  customer: {
    name: string;
    company: string;
    phone: string;
    email: string;
    address: { line1: string; suburb: string; state: string; postcode: string; country: string };
  };
  items: Item[];
  shipments: Shipment[];
  totals: Totals | null;
  catalog_note: string;
  shipping: {
    amount: string;
    method: string;
    complete: boolean;
    origin_postcode: string;
    destination_postcode: string;
    packages: { shipment_id: string; amount: string; method: string; note: string }[];
  };
};
export type Tracking = Shipment & {
  query_state: string;
  status: string | null;
  last_update: string | null;
  last_update_text?: string;
  message: string;
  environment: string | null;
  fetched_at: string | null;
  cached: boolean;
  events: {
    description: string;
    location: string | null;
    date: string | null;
    date_text?: string;
  }[];
};
