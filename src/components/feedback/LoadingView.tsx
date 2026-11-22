import React from "react";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";

export interface LoadingViewProps {
  count?: number;
  type?: "card" | "list" | "table";
  className?: string;
}

export const LoadingView: React.FC<LoadingViewProps> = ({
  count = 3,
  type = "card",
  className,
}) => {
  return (
    <div
      className={cn(
        type === "card"
          ? "grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3"
          : "space-y-4",
        className
      )}
      aria-label="Loading content"
      role="status"
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-[14px] border border-slate-200 bg-white p-5 shadow-sm space-y-4"
        >
          {type === "card" ? (
            <>
              <Skeleton className="h-44 w-full rounded-[10px]" />
              <div className="space-y-2">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
              <div className="pt-2 flex items-center justify-between">
                <Skeleton className="h-6 w-20 rounded-full" />
                <Skeleton className="h-9 w-24 rounded-[8px]" />
              </div>
            </>
          ) : (
            <div className="flex items-center gap-4">
              <Skeleton className="h-12 w-12 rounded-full shrink-0" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            </div>
          )}
        </div>
      ))}
      <span className="sr-only">Loading content...</span>
    </div>
  );
};
