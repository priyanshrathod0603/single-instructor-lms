"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CreditCard,
  Search,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  Check,
  ArrowLeft,
} from "lucide-react";
import { ordersApi } from "@/lib/api/orders";
import { OrderResponse } from "@/types/order";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

export default function AdminOrdersPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  // Refund modal state
  const [refundingOrder, setRefundingOrder] = useState<OrderResponse | null>(null);
  const [refundReason, setRefundReason] = useState("");
  const [refundError, setRefundError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const { data: ordersData, isLoading } = useQuery({
    queryKey: ["all-orders-ledger", statusFilter, page],
    queryFn: () =>
      ordersApi.listAllOrders({
        status: statusFilter || undefined,
        page,
        per_page: 25,
      }),
  });

  const refundMutation = useMutation({
    mutationFn: () => {
      if (!refundingOrder) throw new Error("No order selected");
      return ordersApi.processRefund(refundingOrder.id, {
        reason: refundReason.trim(),
      });
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["all-orders-ledger"] });
      setRefundingOrder(null);
      setRefundReason("");
      setActionMessage(`Refund of ₹${res.amount_inr / 100} processed successfully!`);
      setTimeout(() => setActionMessage(null), 4000);
    },
    onError: (err: any) => {
      setRefundError(err?.message || "Failed to process refund.");
    },
  });

  const formatCurrency = (paise: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(paise / 100);
  };

  return (
    <div className="space-y-6">
      {/* Contextual Back Navigation */}
      <div>
        <Link
          href="/admin"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Admin Dashboard
        </Link>
      </div>

      {/* Header */}
      <div>
        <h1 className="font-heading text-2xl font-bold text-slate-900">
          Commercial Financial Ledger
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Inspect customer orders, verify transaction IDs, and authorize commercial refunds.
        </p>
      </div>

      {actionMessage && (
        <div className="flex items-center gap-2 rounded-lg bg-teal-50 p-4 text-sm text-teal-800 border border-teal-200">
          <CheckCircle2 className="h-5 w-5 text-teal-600 shrink-0" />
          <span>{actionMessage}</span>
        </div>
      )}

      {/* Filter Bar */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setStatusFilter("")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            statusFilter === ""
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          All Orders ({ordersData?.total ?? 0})
        </button>
        <button
          onClick={() => setStatusFilter("PAID")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            statusFilter === "PAID"
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Paid
        </button>
        <button
          onClick={() => setStatusFilter("PENDING")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            statusFilter === "PENDING"
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Pending
        </button>
        <button
          onClick={() => setStatusFilter("REFUNDED")}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            statusFilter === "REFUNDED"
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          Refunded
        </button>
      </div>

      {/* Table */}
      <div className="rounded-[16px] border border-slate-200 bg-white shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary-teal" />
          </div>
        ) : !ordersData?.items?.length ? (
          <div className="p-12 text-center text-slate-500 space-y-2">
            <CreditCard className="h-8 w-8 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-800">No orders found</p>
            <p className="text-xs text-slate-500">Commercial transactions will appear here.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th scope="col" className="px-6 py-4">Order Number & Customer</th>
                  <th scope="col" className="px-6 py-4">Amount</th>
                  <th scope="col" className="px-6 py-4">Status</th>
                  <th scope="col" className="px-6 py-4">Gateway Reference</th>
                  <th scope="col" className="px-6 py-4">Date</th>
                  <th scope="col" className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {ordersData.items.map((order) => (
                  <tr key={order.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-900">{order.order_no}</div>
                      <div className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-xs">
                        Student: {order.student_id}
                      </div>
                    </td>
                    <td className="px-6 py-4 font-bold text-slate-900">
                      {formatCurrency(order.amount_inr)}
                    </td>
                    <td className="px-6 py-4">
                      <Badge variant={order.status === "PAID" ? "success" : "outline"}>
                        {order.status}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-xs font-mono text-slate-500">
                      {order.razorpay_order_id || "—"}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {new Date(order.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {order.status === "PAID" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setRefundError(null);
                            setRefundReason("Student requested refund within 7-day period");
                            setRefundingOrder(order);
                          }}
                          className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                        >
                          <RotateCcw className="h-3.5 w-3.5 mr-1" />
                          Issue Refund
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Refund Modal */}
      {refundingOrder && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="refund-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        >
          <div className="relative w-full max-w-lg rounded-[16px] bg-white p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h2 id="refund-modal-title" className="font-heading text-lg font-bold text-slate-900">
                Authorize Refund: {refundingOrder.order_no}
              </h2>
              <button
                onClick={() => setRefundingOrder(null)}
                className="text-slate-400 hover:text-slate-600 min-h-[44px] min-w-[44px] flex items-center justify-center"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-3 bg-amber-50 rounded-lg text-amber-900 text-xs border border-amber-200">
              Issuing a refund will revoke student course enrollment access automatically via payment webhooks.
            </div>

            {refundError && (
              <div className="flex items-center gap-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-700 border border-rose-200">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
                <span>{refundError}</span>
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                refundMutation.mutate();
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Refund Amount (Paise: {refundingOrder.amount_inr})
                </label>
                <Input
                  value={formatCurrency(refundingOrder.amount_inr)}
                  disabled
                  className="bg-slate-100"
                />
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Mandatory Business Justification *
                </label>
                <Input
                  value={refundReason}
                  onChange={(e) => setRefundReason(e.target.value)}
                  placeholder="Reason for refund (min 5 characters)"
                  required
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
                <Button variant="ghost" size="sm" onClick={() => setRefundingOrder(null)}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={refundReason.trim().length < 5 || refundMutation.isPending}
                  isLoading={refundMutation.isPending}
                  className="bg-rose-600 hover:bg-rose-700"
                >
                  <Check className="h-4 w-4 mr-1.5" />
                  Confirm & Execute Refund
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
