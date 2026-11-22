import { apiClient } from "./client";
import { OrderListResponse, OrderResponse, RefundRequest, RefundResponse } from "@/types/order";

export interface OrderListParams {
  page?: number;
  per_page?: number;
  status?: string;
  student_id?: string;
}

export const ordersApi = {
  /**
   * List orders belonging to the authenticated student (or all if admin).
   */
  async listOwnOrders(params?: OrderListParams): Promise<OrderListResponse> {
    return apiClient.get<OrderListResponse>("/orders", {
      params: {
        page: params?.page ?? 1,
        per_page: params?.per_page ?? 20,
        status: params?.status,
      },
    });
  },

  /**
   * Admin directory listing of all commerce orders with filters.
   */
  async listAllOrders(params?: OrderListParams): Promise<OrderListResponse> {
    return apiClient.get<OrderListResponse>("/orders", {
      params: {
        page: params?.page ?? 1,
        per_page: params?.per_page ?? 20,
        status: params?.status,
        student_id: params?.student_id,
      },
    });
  },

  /**
   * Retrieve a specific order by ID.
   */
  async getOrder(orderId: string): Promise<OrderResponse> {
    return apiClient.get<OrderResponse>(`/orders/${encodeURIComponent(orderId)}`);
  },

  /**
   * Issue a refund for an order (Admin only).
   */
  async processRefund(orderId: string, data: RefundRequest): Promise<RefundResponse> {
    return apiClient.post<RefundResponse>(
      `/orders/${encodeURIComponent(orderId)}/refund`,
      data
    );
  },
};
