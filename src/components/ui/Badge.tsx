import React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "teal" | "coral" | "mint" | "peach" | "outline" | "success" | "warning" | "error";
  size?: "sm" | "md";
}

export const Badge: React.FC<BadgeProps> = ({
  className,
  variant = "mint",
  size = "md",
  children,
  ...props
}) => {
  const variantStyles: Record<NonNullable<BadgeProps["variant"]>, string> = {
    teal: "bg-primary-teal text-white font-medium",
    coral: "bg-accent-coral text-white font-medium",
    mint: "bg-accent-mint text-primary-teal font-medium border border-primary-teal/20",
    peach: "bg-accent-peach text-[#9A3412] font-medium border border-[#FF8964]/30",
    outline: "border border-slate-300 text-slate-700 font-medium bg-transparent",
    success: "bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium",
    warning: "bg-amber-50 text-amber-700 border border-amber-200 font-medium",
    error: "bg-rose-50 text-rose-700 border border-rose-200 font-medium",
  };

  const sizeStyles: Record<NonNullable<BadgeProps["size"]>, string> = {
    sm: "text-xs px-2 py-0.5 rounded-full",
    md: "text-xs sm:text-sm px-2.5 py-1 rounded-full",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-sans font-medium transition-colors select-none",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
