/**
 * TypeScript definitions for SA-05 Complete Commercial Governance.
 * Covers Offers Management, Payment Overview, and Platform Information & Settings.
 * Synchronized with backend schemas:
 * - backend/app/schemas/offer.py
 * - backend/app/schemas/payment_overview.py
 * - backend/app/schemas/settings.py
 */

// ============================================================================
// SA-05.1: Offers Management Types
// ============================================================================

export type DiscountType = "PERCENTAGE" | "FIXED";
export type OfferStatus = "ACTIVE" | "INACTIVE" | "ARCHIVED";

export interface OfferCourseSummary {
  id: string;
  title: string;
  slug: string;
}

export interface OfferCreatorSummary {
  id: string;
  email: string;
  full_name: string;
}

export interface OfferItem {
  id: string;
  name: string;
  code: string;
  description?: string | null;
  discount_type: DiscountType;
  discount_value: number; // 1-100 for PERCENTAGE, or paise for FIXED
  course_id?: string | null;
  course?: OfferCourseSummary | null;
  valid_from: string;
  valid_to: string;
  usage_limit?: number | null;
  times_used: number;
  status: OfferStatus;
  created_by_id: string;
  creator?: OfferCreatorSummary | null;
  created_at: string;
  updated_at: string;
}

export interface OfferListResponse {
  items: OfferItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface OfferCreatePayload {
  name: string;
  code: string;
  description?: string | null;
  discount_type: DiscountType;
  discount_value: number;
  course_id?: string | null;
  valid_from: string;
  valid_to: string;
  usage_limit?: number | null;
  status?: OfferStatus;
}

export interface OfferUpdatePayload {
  name?: string;
  description?: string | null;
  discount_type?: DiscountType;
  discount_value?: number;
  course_id?: string | null;
  valid_from?: string;
  valid_to?: string;
  usage_limit?: number | null;
  status?: OfferStatus;
}

export interface OfferStatusPayload {
  status: OfferStatus;
}

export interface OfferFilterParams {
  search?: string;
  status?: string;
  discount_type?: string;
  page?: number;
  per_page?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}

// ============================================================================
// SA-05.2: Payment Overview Types
// ============================================================================

export interface PaymentMetrics {
  total_transactions_count: number;
  successful_payments_count: number;
  failed_payments_count: number;
  pending_orders_count: number;
  refunded_orders_count: number;
  gross_revenue_paise: number;
  successful_collected_paise: number;
  refunded_amount_paise: number;
  net_collected_paise: number;
  currency: string;
  generated_at: string;
}

export interface TransactionRefundSummary {
  id: string;
  amount_inr: number; // in paise
  reason: string;
  status: string;
  razorpay_refund_id?: string | null;
  processed_at: string;
}

export interface TransactionStudentSummary {
  id: string;
  email: string;
  full_name: string;
}

export interface TransactionCourseSummary {
  id: string;
  title: string;
  slug: string;
}

export interface TransactionOrderSummary {
  id: string;
  order_no: string;
  status: string;
  amount_inr: number; // in paise
  currency: string;
}

export interface TransactionItem {
  id: string;
  gateway: string;
  razorpay_payment_id: string;
  status: "SUCCESS" | "FAILED" | string;
  amount_inr: number; // in paise
  currency: string;
  processed_at: string;
  order?: TransactionOrderSummary | null;
  student?: TransactionStudentSummary | null;
  course?: TransactionCourseSummary | null;
  refunds: TransactionRefundSummary[];
}

export interface TransactionListResponse {
  items: TransactionItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface TransactionFilterParams {
  search?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  page?: number;
  per_page?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}

// ============================================================================
// SA-05.3: Platform Information & Settings Types
// ============================================================================

export interface PublicPlatformInfo {
  // General Platform Branding
  platform_name: string;
  brand_name: string;
  brand_description?: string | null;
  support_email?: string | null;
  support_phone?: string | null;
  logo_url?: string | null;

  // Safe System Context (Read-Only)
  frontend_url: string;
  cdn_stream_base_url: string;
  version: string;
  environment: string;
  currency: string;
  email_provider: string;
  storage_provider: string;
  updated_at?: string | null;
}

export interface PlatformSettingsUpdatePayload {
  platform_name?: string;
  brand_name?: string;
  brand_description?: string | null;
  support_email?: string | null;
  support_phone?: string | null;
  logo_url?: string | null;
}
