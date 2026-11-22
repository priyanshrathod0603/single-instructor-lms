"use client";

import React, { useState, useEffect } from "react";
import { Search, X, SlidersHorizontal } from "lucide-react";
import { Input } from "@/components/ui/Input";

export interface CourseFilterValues {
  search: string;
  tag: string;
  sortBy: "newest" | "price_asc" | "price_desc";
}

interface CourseFiltersProps {
  initialValues: CourseFilterValues;
  availableTags?: string[];
  totalResults?: number;
  onFilterChange: (values: CourseFilterValues) => void;
}

const DEFAULT_TAGS = [
  "Architecture",
  "Backend",
  "Python",
  "System Design",
  "Security",
  "DevOps",
];

export const CourseFilters: React.FC<CourseFiltersProps> = ({
  initialValues,
  availableTags = DEFAULT_TAGS,
  totalResults,
  onFilterChange,
}) => {
  const [searchTerm, setSearchTerm] = useState(initialValues.search);
  const [selectedTag, setSelectedTag] = useState(initialValues.tag);
  const [sortBy, setSortBy] = useState<"newest" | "price_asc" | "price_desc">(
    initialValues.sortBy
  );

  const prevInitialSearch = React.useRef(initialValues.search);

  // Sync internal search when parent initialValues change externally
  useEffect(() => {
    if (prevInitialSearch.current !== initialValues.search) {
      prevInitialSearch.current = initialValues.search;
      setSearchTerm(initialValues.search);
    }
  }, [initialValues.search]);

  // Debounced search trigger
  useEffect(() => {
    const handler = setTimeout(() => {
      if (searchTerm !== initialValues.search) {
        prevInitialSearch.current = searchTerm;
        onFilterChange({
          search: searchTerm,
          tag: selectedTag,
          sortBy,
        });
      }
    }, 350);

    return () => clearTimeout(handler);
  }, [searchTerm, selectedTag, sortBy, initialValues.search, onFilterChange]);

  const handleTagSelect = (tag: string) => {
    const nextTag = selectedTag === tag ? "" : tag;
    setSelectedTag(nextTag);
    onFilterChange({
      search: searchTerm,
      tag: nextTag,
      sortBy,
    });
  };

  const handleSortChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const nextSort = e.target.value as "newest" | "price_asc" | "price_desc";
    setSortBy(nextSort);
    onFilterChange({
      search: searchTerm,
      tag: selectedTag,
      sortBy: nextSort,
    });
  };

  const handleClearSearch = () => {
    setSearchTerm("");
    prevInitialSearch.current = "";
    onFilterChange({
      search: "",
      tag: selectedTag,
      sortBy,
    });
  };

  const handleResetAll = () => {
    setSearchTerm("");
    prevInitialSearch.current = "";
    setSelectedTag("");
    setSortBy("newest");
    onFilterChange({
      search: "",
      tag: "",
      sortBy: "newest",
    });
  };

  const hasActiveFilters = Boolean(searchTerm || selectedTag || sortBy !== "newest");

  return (
    <div className="space-y-4">
      {/* Top Search Bar & Sort Dropdown */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        {/* Search input with debouncing */}
        <div className="relative flex-1">
          <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
            <Search className="h-4 w-4" />
          </div>
          <input
            type="text"
            role="searchbox"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search courses by topic, title, or keyword..."
            aria-label="Search courses"
            className="w-full h-11 pl-10 pr-10 rounded-lg border border-soft-peach bg-white font-sans text-sm text-slate-900 placeholder:text-slate-400 shadow-subtle focus:border-primary-teal focus:outline-none focus:ring-2 focus:ring-primary-teal/20 transition-all"
          />
          {searchTerm && (
            <button
              type="button"
              onClick={handleClearSearch}
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 focus:outline-none"
              aria-label="Clear search text"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Sort Select */}
        <div className="flex items-center gap-2 shrink-0">
          <label htmlFor="course-sort" className="sr-only">
            Sort Courses By
          </label>
          <div className="relative">
            <select
              id="course-sort"
              value={sortBy}
              onChange={handleSortChange}
              aria-label="Sort courses"
              className="h-11 rounded-lg border border-soft-peach bg-white px-3.5 pr-8 font-sans text-sm font-medium text-slate-700 shadow-subtle focus:border-primary-teal focus:outline-none focus:ring-2 focus:ring-primary-teal/20 transition-all appearance-none cursor-pointer"
            >
              <option value="newest">Sort: Newest First</option>
              <option value="price_asc">Price: Low to High</option>
              <option value="price_desc">Price: High to Low</option>
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2.5 text-slate-400">
              <SlidersHorizontal className="h-3.5 w-3.5" />
            </div>
          </div>
        </div>
      </div>

      {/* Tag Filters Row */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button
          type="button"
          onClick={() => handleTagSelect("")}
          className={`h-8 rounded-full px-3.5 text-xs font-semibold transition-all ${
            selectedTag === ""
              ? "bg-primary-teal text-white shadow-sm"
              : "bg-white border border-soft-peach text-slate-600 hover:border-primary-teal hover:text-primary-teal"
          }`}
        >
          All Topics
        </button>

        {availableTags.map((tag) => {
          const isSelected = selectedTag.toLowerCase() === tag.toLowerCase();
          return (
            <button
              key={tag}
              type="button"
              onClick={() => handleTagSelect(tag)}
              className={`h-8 rounded-full px-3.5 text-xs font-semibold transition-all ${
                isSelected
                  ? "bg-primary-teal text-white shadow-sm"
                  : "bg-white border border-soft-peach text-slate-600 hover:border-primary-teal hover:text-primary-teal"
              }`}
            >
              {tag}
            </button>
          );
        })}

        {hasActiveFilters && (
          <button
            type="button"
            onClick={handleResetAll}
            className="ml-auto text-xs font-medium text-accent-coral hover:underline focus:outline-none"
          >
            Reset All Filters
          </button>
        )}
      </div>

      {/* Result Counter */}
      {typeof totalResults === "number" && (
        <div className="text-xs text-slate-500 font-sans pt-1">
          Showing <span className="font-semibold text-slate-800">{totalResults}</span>{" "}
          {totalResults === 1 ? "course" : "courses"}
          {selectedTag && <span> in topic &ldquo;{selectedTag}&rdquo;</span>}
          {searchTerm && <span> matching &ldquo;{searchTerm}&rdquo;</span>}
        </div>
      )}
    </div>
  );
};
