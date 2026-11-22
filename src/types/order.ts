/**
 * TypeScript definitions for Student Orders, Commerce, and Refunds.
 * Synchronized with backend: backend/app/schemas/order.py
 */

export interface OrderResponse {
  id: string;
  order_no: string;
  student_id: string;
  course_id: string;
  amount_inr: number; // in paise
  currency: string;
  status: "PENDING" | "PAID" | "FAILED" | "REFUNDED" | "PARTIALLY_REFUNDED" | string;
  razorpay_order_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OrderListResponse {
  items: OrderResponse[];
  total: number;
  page: number;
  size: number;
}

export interface RefundRequest {
  reason: string;
  amount_inr?: number; // In paise. Defaults to full order total if omitted
}

export interface RefundResponse {
  id: string;
  order_id: string;
  amount_inr: number;
  reason: string;
  status: string;
  razorpay_refund_id?: string | null;
  approved_by: string;
  processed_at: string;
}
