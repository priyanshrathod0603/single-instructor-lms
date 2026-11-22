import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", label, error, helperText, id, ...props }, ref) => {
    const generatedId = React.useId();
    const inputId = id || generatedId;
    const errorId = error ? `${inputId}-error` : undefined;
    const helperId = helperText ? `${inputId}-helper` : undefined;

    return (
      <div className="w-full space-y-1.5 text-left">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-semibold text-text-primary"
          >
            {label}
          </label>
        )}
        <input
          id={inputId}
          ref={ref}
          type={type}
          aria-invalid={!!error}
          aria-describedby={errorId || helperId}
          className={cn(
            "flex w-full h-11 px-3.5 py-2.5 rounded-md bg-brand-white border transition-colors touch-target",
            "text-base text-text-primary placeholder:text-text-muted",
            "border-brand-peach focus:border-brand-teal focus:outline-none focus:ring-2 focus:ring-brand-teal focus:ring-offset-1",
            "disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-50",
            error && "border-status-error focus:ring-status-error focus:border-status-error",
            className
          )}
          {...props}
        />
        {error && (
          <p id={errorId} role="alert" className="text-xs font-medium text-status-error">
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

Input.displayName = "Input";
