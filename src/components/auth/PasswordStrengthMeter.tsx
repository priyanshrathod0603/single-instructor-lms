import React from "react";
import { cn } from "@/lib/utils";

interface PasswordStrengthMeterProps {
  password?: string;
  className?: string;
}

export const PasswordStrengthMeter: React.FC<PasswordStrengthMeterProps> = ({
  password = "",
  className,
}) => {
  const calculateScore = (pwd: string): { score: number; label: string; color: string } => {
    if (!pwd) return { score: 0, label: "Enter password", color: "bg-slate-200" };

    let score = 0;
    if (pwd.length >= 12) score += 1;
    if (pwd.length >= 16) score += 1;
    if (/[A-Z]/.test(pwd) && /[a-z]/.test(pwd)) score += 1;
    if (/[0-9]/.test(pwd)) score += 1;
    if (/[^A-Za-z0-9]/.test(pwd)) score += 1;

    if (score <= 1) return { score: 1, label: "Weak (minimum 12 chars required)", color: "bg-rose-500" };
    if (score <= 3) return { score: 2, label: "Moderate", color: "bg-amber-500" };
    if (score === 4) return { score: 3, label: "Strong", color: "bg-emerald-500" };
    return { score: 4, label: "Very Strong", color: "bg-primary-teal" };
  };

  const { score, label, color } = calculateScore(password);

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex gap-1.5 h-1.5 w-full">
        {[1, 2, 3, 4].map((step) => (
          <div
            key={step}
            className={cn(
              "flex-1 rounded-full transition-all duration-300",
              score >= step ? color : "bg-slate-200"
            )}
          />
        ))}
      </div>
      {password && (
        <p className="text-xs text-slate-500 font-sans">{label}</p>
      )}
    </div>
  );
};
