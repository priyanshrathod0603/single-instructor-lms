import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";

export interface ErrorAlertProps {
  title?: string;
  message: string;
  requestId?: string;
  onRetry?: () => void;
  className?: string;
}

export const ErrorAlert: React.FC<ErrorAlertProps> = ({
  title = "Something went wrong",
  message,
  requestId,
  onRetry,
  className,
}) => {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-[12px] border border-rose-200 bg-rose-50/80 p-4 text-rose-900 shadow-sm",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0 text-rose-600">
          <AlertCircle className="h-5 w-5" />
        </div>
        <div className="flex-1 space-y-1">
          <h4 className="font-sans text-sm font-semibold">{title}</h4>
          <p className="font-sans text-sm text-rose-800 leading-relaxed">
            {message}
          </p>
          {requestId && (
            <p className="font-mono text-xs text-rose-500">
              Request ID: {requestId}
            </p>
          )}
        </div>
        {onRetry && (
          <div className="shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={onRetry}
              className="border-rose-300 text-rose-800 hover:bg-rose-100 hover:text-rose-900 min-h-[36px]"
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              Retry
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
