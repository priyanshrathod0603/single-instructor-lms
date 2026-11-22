"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React, { useState } from "react";
import { Toaster } from "sonner";
import { DisplacedSessionModal } from "@/components/feedback/DisplacedSessionModal";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 1000 * 60, // 1 minute
            refetchOnWindowFocus: false,
            retry: (failureCount, error: any) => {
              // Never retry client auth or permission errors
              const status = error?.status || error?.statusCode;
              if (status === 401 || status === 403 || status === 404) {
                return false;
              }
              return failureCount < 2;
            },
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <DisplacedSessionModal />
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "var(--color-warm-cream)",
            color: "var(--color-text-primary)",
            borderColor: "var(--color-soft-peach)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-card)",
            fontSize: "14px",
          },
        }}
      />
    </QueryClientProvider>
  );
}
