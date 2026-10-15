/** Shared API envelope returned by the FastAPI backend. */
export type ApiResponse<T> = { data: T; meta?: Record<string, unknown> };

export type Health = {
  status: 'ok' | 'degraded';
  database: 'ok' | 'unavailable';
  shop_database: 'ok' | 'unavailable';
  provider: 'ollama' | 'opencode';
  ai_availability: 'available' | 'unavailable';
  ollama: 'available' | 'unavailable';
  model: string;
  model_available: boolean;
  demo_mode: boolean;
  integration_mode: 'local_store' | 'not_connected';
};

export type ChatIntent = 'shop_summary' | 'inventory_query' | 'change_price' | 'product_search' | 'sales_advice' | 'create_product' | 'unknown';
export type ChatFallbackReason = 'provider_unavailable' | 'provider_timeout' | 'model_unavailable' | 'invalid_response' | 'provider_rejected' | 'free_model_unavailable' | 'tool_not_allowed';

export type PriceProposal = {
  id: number;
  kind: 'change_price';
  status: 'pending' | 'approved' | 'rejected' | 'conflict';
  target_kind: 'product' | 'variant';
  sku: string;
  product_name: string;
  old_price_vnd: number;
  new_price_vnd: number;
  created_at: string;
  decided_at: string | null;
  idempotent: boolean;
};

export type ProductDraft = {
  id: number;
  status: 'collecting' | 'ready' | 'published' | 'cancelled' | 'conflict';
  preview_url: string;
  preview_urls: string[];
  image_count: number;
  name: string | null;
  description: string | null;
  category_id: number | null;
  category_name: string | null;
  price_vnd: number | null;
  stock: number | null;
  sku: string | null;
  missing_fields: string[];
  published_product_id: number | null;
  created_at: string;
  decided_at: string | null;
};

export type ChatData = {
  run_id: number;
  conversation_id: string | null;
  answer: string;
  intent: ChatIntent;
  mode: 'ai' | 'fallback';
  provider: 'ollama' | 'opencode' | 'deterministic_parser';
  model: string | null;
  fallback_reason: ChatFallbackReason | null;
  tool: string | null;
  facts: Record<string, unknown>;
  proposal: PriceProposal | null;
  product_draft: ProductDraft | null;
  integration_mode: 'local_store';
  suggestions: string[];
};

export type StoreProduct = {
  id: number; name: string; sku: string; price_vnd: number; stock: number;
  status: string; image_url: string | null; sold_count: number; rating: number;
};
export type StoreOrder = {
  id: number; customer_name: string; total_vnd: number; status: string;
  created_at: string; item_count: number; quantity: number;
  payment_method: string | null; payment_status: string | null;
  shipping_fee: number | null; discount_amount: number | null;
  items: { id: number; quantity: number; price_vnd: number; name: string | null; sku: string | null; variant_title: string | null; image_url: string | null }[];
};
export type StorePage<T> = { items: T[]; total: number; limit: number; offset: number };
export type ManagementData = {
  shop: { name: string; slug: string; rating: number; followers: number; location: string; vacation_mode: boolean };
  days: number; from_date: string; to_date: string; updated_at: string; timezone: string;
  order_value_vnd: number; order_count: number; delivered_value_vnd: number;
  average_order_vnd: number; cancelled_count: number; previous_value_vnd: number;
  change_percent: number | null; series: { date: string; value: number }[];
  order_status_counts: Record<string, number>;
  tasks: { pending_orders: number; packing_orders: number; shipping_orders: number; low_stock_products: number; unanswered_reviews: number };
  active_products: number; top_products: StoreProduct[]; integration_mode: 'local_store';
};
export type ConversationSummary = { id: string; title: string; updated_at: string; turns: number };
export type ConversationDetail = { id: string; turns: { message: string; response: ChatData; created_at: string }[] };
