import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "accent" | "outline" | "ghost" | "destructive";
  size?: "default" | "sm" | "lg" | "icon";
  isLoading?: boolean;
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "primary",
      size = "default",
      isLoading = false,
      asChild = false,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const Comp = asChild ? Slot : "button";

    const variantClasses = {
      primary: cn(
        "bg-brand-teal text-brand-white shadow-sm border border-transparent",
        "hover:bg-brand-teal-dark hover:-translate-y-0.5 hover:scale-[1.02] hover:shadow-card",
        "active:translate-y-0 active:scale-[0.98] active:shadow-sm"
      ),
      secondary: cn(
        "bg-white text-text-primary border border-soft-peach shadow-subtle",
        "hover:bg-brand-peach/40 hover:border-brand-teal/40 hover:text-brand-teal hover:-translate-y-0.5 hover:scale-[1.02] hover:shadow-card",
        "active:translate-y-0 active:scale-[0.98] active:bg-brand-peach/60 active:shadow-subtle"
      ),
      accent: cn(
        "bg-brand-coral text-brand-white shadow-sm border border-transparent",
        "hover:bg-brand-coral-dark hover:-translate-y-0.5 hover:scale-[1.02] hover:shadow-card",
        "active:translate-y-0 active:scale-[0.98] active:shadow-sm"
      ),
      outline: cn(
        "bg-transparent border-2 border-brand-teal text-brand-teal",
        "hover:bg-brand-mint/40 hover:border-brand-teal-dark hover:text-brand-teal-dark hover:-translate-y-0.5 hover:scale-[1.02] hover:shadow-sm",
        "active:translate-y-0 active:scale-[0.98] active:bg-brand-mint/60"
      ),
      ghost: cn(
        "bg-transparent text-text-primary border border-transparent",
        "hover:bg-brand-peach/60 hover:text-brand-teal",
        "active:bg-brand-peach active:scale-[0.98]"
      ),
      destructive: cn(
        "bg-status-error text-brand-white shadow-sm border border-transparent",
        "hover:bg-red-700 hover:-translate-y-0.5 hover:scale-[1.02] hover:shadow-card",
        "active:translate-y-0 active:scale-[0.98] active:shadow-sm"
      ),
    }[variant];

    const sizeClasses = {
      default: "h-11 px-5 text-sm touch-target",
      sm: "h-9 px-3.5 text-xs rounded-md",
      lg: "h-12 px-6 text-base touch-target",
      icon: "h-11 w-11 p-0 touch-target flex items-center justify-center",
    }[size];

    return (
      <Comp
        ref={ref}
        disabled={disabled || isLoading}
        aria-busy={isLoading || undefined}
        className={cn(
          "group inline-flex items-center justify-center gap-2 rounded-md font-semibold select-none cursor-pointer",
          "transition-all duration-200 ease-out will-change-transform",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal focus-visible:ring-offset-2",
          "disabled:opacity-50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:transform-none disabled:hover:scale-100 disabled:hover:translate-y-0 disabled:shadow-none",
          "[&_svg.lucide-arrow-right]:transition-transform [&_svg.lucide-arrow-right]:duration-200 group-hover:[&_svg.lucide-arrow-right]:translate-x-1",
          "[&_svg.lucide-chevron-right]:transition-transform [&_svg.lucide-chevron-right]:duration-200 group-hover:[&_svg.lucide-chevron-right]:translate-x-0.5",
          "motion-reduce:transform-none motion-reduce:transition-none",
          variantClasses,
          sizeClasses,
          className
        )}
        {...props}
      >
        {asChild ? (
          children
        ) : (
          <>
            {isLoading && <Loader2 className="h-4 w-4 animate-spin text-current shrink-0" />}
            {children}
          </>
        )}
      </Comp>
    );
  }
);

Button.displayName = "Button";
