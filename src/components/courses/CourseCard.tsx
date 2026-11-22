"use client";

import React, { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { BookOpen, Sparkles, ArrowRight, Clock } from "lucide-react";
import { CourseSummary } from "@/types/course";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatCurrency } from "@/lib/utils";

interface CourseCardProps {
  course: CourseSummary;
  className?: string;
}

export const CourseCard: React.FC<CourseCardProps> = ({ course, className }) => {
  const [imageError, setImageError] = useState(false);
  const courseUrl = `/courses/${course.slug || course.id}`;

  return (
    <Card
      className={`group relative flex h-full flex-col overflow-hidden transition-all duration-200 hover:-translate-y-1 hover:shadow-elevated hover:border-primary-teal/40 active:scale-[0.99] ${
        className || ""
      }`}
    >
      {/* 16:9 Thumbnail Header */}
      <div className="relative aspect-video w-full overflow-hidden bg-slate-100">
        {course.thumbnail_url && !imageError ? (
          <Image
            src={course.thumbnail_url}
            alt={course.title}
            fill
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            className="object-cover transition-transform duration-300 group-hover:scale-105"
            onError={() => setImageError(true)}
            unoptimized={course.thumbnail_url.startsWith("http")}
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-primary-teal/15 via-accent-mint/30 to-soft-peach/40 p-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white shadow-subtle text-primary-teal">
              <BookOpen className="h-6 w-6" />
            </div>
            <span className="mt-2 text-xs font-semibold uppercase tracking-wider text-primary-teal/80">
              Masterclass
            </span>
          </div>
        )}

        {/* Free / Status Badge Overlay */}
        <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
          {course.is_free ? (
            <Badge variant="mint" size="sm" className="shadow-sm font-bold">
              FREE
            </Badge>
          ) : (
            course.tags.length > 0 && (
              <Badge variant="outline" size="sm" className="bg-white/90 backdrop-blur-sm text-slate-800 shadow-sm font-medium">
                {course.tags[0]}
              </Badge>
            )
          )}
        </div>
      </div>

      {/* Card Content */}
      <div className="flex flex-1 flex-col p-5 sm:p-6 justify-between space-y-4">
        <div className="space-y-2">
          {/* Tags list if not free */}
          {!course.is_free && course.tags.length > 1 && (
            <div className="flex flex-wrap gap-1">
              {course.tags.slice(1, 3).map((tag) => (
                <span
                  key={tag}
                  className="rounded px-1.5 py-0.5 text-[11px] font-medium bg-soft-peach/60 text-slate-600"
                >
                  #{tag}
                </span>
              ))}
            </div>
          )}

          <Link href={courseUrl} className="focus:outline-none">
            <h3 className="font-heading text-lg font-bold text-slate-900 group-hover:text-primary-teal transition-colors line-clamp-2">
              {course.title}
            </h3>
          </Link>

          {course.headline && (
            <p className="font-sans text-sm text-slate-600 line-clamp-2 leading-relaxed">
              {course.headline}
            </p>
          )}
        </div>

        {/* Footer with Price and View Link */}
        <div className="pt-4 border-t border-soft-peach/60 flex items-center justify-between">
          <div>
            <span className="block text-[11px] uppercase tracking-wider font-semibold text-slate-400">
              Tuition
            </span>
            <span className="font-sans text-lg font-extrabold text-slate-900">
              {course.is_free
                ? "Free Access"
                : formatCurrency(course.price_inr, "INR")}
            </span>
          </div>

          <Button
            asChild
            variant="outline"
            size="sm"
            className="h-9 px-3 text-xs border-soft-peach hover:border-primary-teal"
          >
            <Link
              href={courseUrl}
              aria-label={`View curriculum for ${course.title}`}
            >
              Explore
              <ArrowRight className="ml-1 h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
      </div>
    </Card>
  );
};
