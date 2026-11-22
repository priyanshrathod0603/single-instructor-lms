import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combines conditional class names with Tailwind class deduplication.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format currency amounts in paise (BIGINT) to display INR format.
 * E.g., 49900 -> "₹499.00"
 */
export function formatCurrency(amountInPaise: number | bigint, currency: string = "INR"): string {
  const numeric = typeof amountInPaise === "bigint" ? Number(amountInPaise) : amountInPaise;
  const major = numeric / 100;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 2,
  }).format(major);
}
