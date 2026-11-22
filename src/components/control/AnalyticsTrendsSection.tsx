"use client";

import React, { useState } from "react";
import { TrendingUp, UserPlus, GraduationCap, Calendar } from "lucide-react";
import { DailyTrendPoint } from "@/types/control";

interface AnalyticsTrendsSectionProps {
  registrationTrends: DailyTrendPoint[];
  enrollmentTrends: DailyTrendPoint[];
}

function formatDateShort(dateStr: string): string {
  try {
    const parts = dateStr.split("-");
    if (parts.length === 3) {
      const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const monthIndex = parseInt(parts[1], 10) - 1;
      const day = parseInt(parts[2], 10);
      return `${monthNames[monthIndex] || ""} ${day}`;
    }
  } catch {
    // fallback
  }
  return dateStr;
}

interface TrendBarChartProps {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  data: DailyTrendPoint[];
  barColorClass: string;
  barHoverColorClass: string;
  badgeColorClass: string;
  unitLabel: string;
}

const TrendBarChart: React.FC<TrendBarChartProps> = ({
  title,
  subtitle,
  icon,
  data,
  barColorClass,
  barHoverColorClass,
  badgeColorClass,
  unitLabel,
}) => {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const totalCount = data.reduce((sum, item) => sum + item.count, 0);
  const maxCount = Math.max(...data.map((d) => d.count), 0);
  const chartCeiling = maxCount > 0 ? maxCount : 5; // minimum grid ceiling of 5

  return (
    <div className="rounded-[16px] border border-slate-200 bg-white p-5 sm:p-6 shadow-sm flex flex-col justify-between">
      {/* Header */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className={`p-2 rounded-lg ${badgeColorClass}`}>{icon}</div>
            <div>
              <h3 className="font-heading text-base font-bold text-slate-900">{title}</h3>
              <p className="text-xs text-slate-500">{subtitle}</p>
            </div>
          </div>
          <div className="text-right">
            <span className="text-2xl font-extrabold text-slate-900">{totalCount}</span>
            <span className="text-xs text-slate-500 block">14-Day Total</span>
          </div>
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="mt-6">
        {/* Relative chart container */}
        <div className="relative h-44 w-full flex flex-col justify-end pt-6 pb-2">
          {/* Background grid lines */}
          <div className="absolute inset-0 flex flex-col justify-between pointer-events-none opacity-20">
            <div className="border-b border-dashed border-slate-300 w-full" />
            <div className="border-b border-dashed border-slate-300 w-full" />
            <div className="border-b border-slate-200 w-full" />
          </div>

          {/* Tooltip Overlay */}
          {hoveredIndex !== null && data[hoveredIndex] && (
            <div
              className="absolute -top-3 z-20 px-2.5 py-1 rounded bg-slate-900 text-white text-xs shadow-md pointer-events-none transform -translate-x-1/2 transition-all duration-75 whitespace-nowrap"
              style={{
                left: `${((hoveredIndex + 0.5) / data.length) * 100}%`,
              }}
            >
              <div className="font-semibold">
                {data[hoveredIndex].count} {unitLabel}
                {data[hoveredIndex].count === 1 ? "" : "s"}
              </div>
              <div className="text-[10px] text-slate-300">
                {formatDateShort(data[hoveredIndex].date)}
              </div>
            </div>
          )}

          {/* Bar Columns */}
          <div className="flex items-end justify-between gap-1 sm:gap-2 h-full z-10">
            {data.map((point, idx) => {
              const heightPercent =
                maxCount === 0
                  ? 2
                  : Math.max(4, Math.round((point.count / chartCeiling) * 100));

              const isHovered = hoveredIndex === idx;

              return (
                <div
                  key={point.date}
                  className="flex-1 flex flex-col items-center h-full justify-end group cursor-pointer focus:outline-none"
                  onMouseEnter={() => setHoveredIndex(idx)}
                  onMouseLeave={() => setHoveredIndex(null)}
                  onFocus={() => setHoveredIndex(idx)}
                  onBlur={() => setHoveredIndex(null)}
                  tabIndex={0}
                  role="img"
                  aria-label={`${formatDateShort(point.date)}: ${point.count} ${unitLabel}`}
                >
                  <div
                    style={{ height: `${heightPercent}%` }}
                    className={`w-full rounded-t transition-all duration-150 ${
                      point.count > 0
                        ? isHovered
                          ? barHoverColorClass
                          : barColorClass
                        : "bg-slate-100 hover:bg-slate-200"
                    }`}
                  />
                </div>
              );
            })}
          </div>
        </div>

        {/* X-Axis Date Labels */}
        <div className="flex items-center justify-between text-[10px] font-medium text-slate-600 mt-2 px-0.5 border-t border-slate-100 pt-2">
          {data.length > 0 && (
            <>
              <span>{formatDateShort(data[0].date)}</span>
              <span className="hidden sm:inline">
                {formatDateShort(data[Math.floor(data.length / 2)].date)}
              </span>
              <span>{formatDateShort(data[data.length - 1].date)}</span>
            </>
          )}
        </div>
      </div>

      {/* Footer / Summary stats */}
      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
        <span className="flex items-center gap-1">
          <Calendar className="h-3.5 w-3.5" />
          Rolling 14 Days
        </span>
        <span>
          Daily Avg:{" "}
          <strong className="text-slate-800 font-semibold">
            {(totalCount / (data.length || 1)).toFixed(1)}
          </strong>
        </span>
      </div>
    </div>
  );
};

export const AnalyticsTrendsSection: React.FC<AnalyticsTrendsSectionProps> = ({
  registrationTrends,
  enrollmentTrends,
}) => {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-heading text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
            Activity & Growth Velocity
          </h2>
          <p className="text-xs sm:text-sm text-slate-500">
            Real daily activity trends recorded over the rolling 14-day window.
          </p>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-semibold text-primary-teal bg-teal-50 px-3 py-1.5 rounded-full border border-teal-100">
          <TrendingUp className="h-3.5 w-3.5" />
          <span>Continuous Ledger</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        {/* Student Registrations Trend */}
        <TrendBarChart
          title="Daily Registrations"
          subtitle="New student accounts created"
          icon={<UserPlus className="h-4 w-4" />}
          data={registrationTrends}
          barColorClass="bg-primary-teal"
          barHoverColorClass="bg-teal-700"
          badgeColorClass="bg-teal-50 text-primary-teal"
          unitLabel="registration"
        />

        {/* Course Enrollments Trend */}
        <TrendBarChart
          title="Daily Enrollments"
          subtitle="Course access grants confirmed"
          icon={<GraduationCap className="h-4 w-4" />}
          data={enrollmentTrends}
          barColorClass="bg-[#FF8964]"
          barHoverColorClass="bg-[#E0724F]"
          badgeColorClass="bg-amber-50 text-[#FF8964]"
          unitLabel="enrollment"
        />
      </div>
    </div>
  );
};
