"use client";

import React from "react";
import Link from "next/link";
import { Receipt, CreditCard, ArrowRight, ArrowLeft, CheckCircle, Clock, AlertCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { ordersApi } from "@/lib/api/orders";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorAlert } from "@/components/feedback/ErrorAlert";
import { formatCurrency } from "@/lib/utils";

export default function StudentOrdersPage() {
  const {
    data: ordersData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["student-orders"],
    queryFn: () => ordersApi.listOwnOrders({ page: 1, per_page: 50 }),
  });

  const orders = ordersData?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Contextual Back Navigation */}
      <div>
        <Link
          href="/app"
          className="inline-flex items-center text-sm font-semibold text-primary-teal hover:underline gap-1.5"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Overview
        </Link>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Order Receipts & Payment History
          </h1>
          <p className="font-sans text-sm text-slate-600 mt-1">
            Review your course purchases, transaction receipts, and payment statuses.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="p-5 space-y-2">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-4 w-full" />
            </Card>
          ))}
        </div>
      ) : isError ? (
        <ErrorAlert
          title="Could not load orders"
          message={error?.message || "Failed to retrieve order history."}
          onRetry={() => refetch()}
        />
      ) : orders.length === 0 ? (
        <EmptyState
          icon={<Receipt className="h-8 w-8 text-primary-teal" />}
          title="No Orders Found"
          description="You haven't made any course purchases yet. Explore our course catalog to get started."
          actionLabel="Browse Courses"
          onAction={() => {
            window.location.href = "/courses";
          }}
        />
      ) : (
        <div className="rounded-[12px] border border-slate-200 bg-white shadow-card divide-y divide-slate-100 overflow-hidden">
          {orders.map((order) => {
            const isPaid = order.status === "PAID";
            const isPending = order.status === "PENDING";
            const isRefunded = order.status === "REFUNDED" || order.status === "PARTIALLY_REFUNDED";

            return (
              <div
                key={order.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between p-5 gap-4 hover:bg-slate-50/50 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-lg shrink-0 ${
                      isPaid
                        ? "bg-emerald-100 text-emerald-700"
                        : isRefunded
                        ? "bg-rose-100 text-rose-700"
                        : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    <Receipt className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-heading text-sm sm:text-base font-bold text-slate-900">
                        Order #{order.order_no}
                      </h3>
                      <Badge
                        variant={isPaid ? "mint" : isRefunded ? "error" : "coral"}
                        size="sm"
                      >
                        {order.status}
                      </Badge>
                    </div>

                    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono text-slate-500">
                      <span>Date: {new Date(order.created_at).toLocaleDateString()}</span>
                      {order.razorpay_order_id && (
                        <span>Ref: {order.razorpay_order_id}</span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <span className="font-heading text-base font-bold text-slate-900 block">
                    {formatCurrency(order.amount_inr)}
                  </span>
                  <span className="font-mono text-[11px] text-slate-400">
                    {order.currency}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
