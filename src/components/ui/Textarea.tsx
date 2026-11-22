import * as React from "react";
import { cn } from "@/lib/utils";

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, error, helperText, id, rows = 4, ...props }, ref) => {
    const generatedId = React.useId();
    const textareaId = id || generatedId;
    const errorId = error ? `${textareaId}-error` : undefined;
    const helperId = helperText ? `${textareaId}-helper` : undefined;

    return (
      <div className="w-full space-y-1.5 text-left">
        {label && (
          <label
            htmlFor={textareaId}
            className="block text-sm font-semibold text-text-primary"
          >
            {label}
          </label>
        )}
        <textarea
          id={textareaId}
          ref={ref}
          rows={rows}
          aria-invalid={!!error}
          aria-describedby={errorId || helperId}
          className={cn(
            "flex w-full px-3.5 py-2.5 rounded-md bg-brand-white border transition-colors",
            "text-base text-text-primary placeholder:text-text-muted",
            "border-brand-peach focus:border-brand-teal focus:outline-none focus:ring-2 focus:ring-brand-teal focus:ring-offset-1",
            "disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-50",
            error && "border-status-error focus:ring-status-error focus:border-status-error",
            className
          )}
          {...props}
        />
        {error && (
          <p id={errorId} className="text-xs font-medium text-status-error">
            {error}
          </p>
        )}
        {!error && helperText && (
          <p id={helperId} className="text-xs text-text-secondary">
            {helperText}
          </p>
        )}
      </div>
    );
  }
);

Textarea.displayName = "Textarea";
