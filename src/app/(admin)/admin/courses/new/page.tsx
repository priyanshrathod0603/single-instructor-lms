"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookMarked, Check, AlertCircle } from "lucide-react";
import { coursesApi } from "@/lib/api/courses";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";

export default function NewCoursePage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [title, setTitle] = useState("");
  const [headline, setHeadline] = useState("");
  const [description, setDescription] = useState("");
  const [priceInRupees, setPriceInRupees] = useState("4999");
  const [isFree, setIsFree] = useState(false);
  const [tagsInput, setTagsInput] = useState("Architecture, Full-Stack");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => {
      const tags = tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const pricePaise = isFree ? 0 : Math.round(parseFloat(priceInRupees || "0") * 100);

      return coursesApi.createCourse({
        title,
        headline,
        description,
        price_inr: pricePaise,
        is_free: isFree,
        tags,
      });
    },
    onSuccess: (course) => {
      queryClient.invalidateQueries({ queryKey: ["manage-courses"] });
      router.push(`/admin/courses/${course.id}/edit`);
    },
    onError: (err: any) => {
      setErrorMessage(err?.message || "Failed to create course. Please review the inputs.");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setErrorMessage("Course title is required.");
      return;
    }
    setErrorMessage(null);
    createMutation.mutate();
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Top Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Link href="/admin/courses" className="hover:text-slate-800 flex items-center gap-1">
          <ArrowLeft className="h-4 w-4" />
          <span>Courses</span>
        </Link>
        <span>/</span>
        <span className="text-slate-900 font-semibold">New Course</span>
      </div>

      <div className="rounded-[16px] border border-slate-200 bg-white p-6 sm:p-8 shadow-sm space-y-6">
        <div>
          <h1 className="font-heading text-2xl font-bold text-slate-900">
            Create Course Entity
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Initialize a new course. An initial working draft revision will be created automatically.
          </p>
        </div>

        {errorMessage && (
          <div className="flex items-center gap-2 rounded-lg bg-rose-50 p-3.5 text-sm text-rose-700 border border-rose-200">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Course Title *
            </label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Master Class: Modern Scalable Architecture"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Course Headline
            </label>
            <Input
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder="A punchy 1-sentence pedagogical summary for the course card"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Course Description
            </label>
            <Textarea
              rows={5}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Detailed syllabus overview, prerequisites, and learning outcomes..."
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                Pricing (INR ₹)
              </label>
              <Input
                type="number"
                disabled={isFree}
                value={priceInRupees}
                onChange={(e) => setPriceInRupees(e.target.value)}
                placeholder="4999"
              />
            </div>

            <div className="flex items-center gap-3 pt-6">
              <input
                type="checkbox"
                id="is-free-check"
                checked={isFree}
                onChange={(e) => setIsFree(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-primary-teal focus:ring-primary-teal"
              />
              <label htmlFor="is-free-check" className="text-sm font-semibold text-slate-800">
                Offer this course for Free
              </label>
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Topic Tags (Comma Separated)
            </label>
            <Input
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder="TypeScript, Architecture, Backend, Cloud"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
            <Link href="/admin/courses">
              <Button variant="ghost" size="default">
                Cancel
              </Button>
            </Link>
            <Button
              type="submit"
              variant="primary"
              size="default"
              isLoading={createMutation.isPending}
            >
              <Check className="h-4 w-4 mr-2" />
              Create Course & Start Curriculum
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
