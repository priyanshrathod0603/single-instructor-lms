"use client";

import React, { useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/Button";

export interface TagInputFieldProps {
  id: string;
  label: string;
  tags: string[];
  onChange: (nextTags: string[]) => void;
  maxTags?: number;
  error?: string;
}

export const TagInputField: React.FC<TagInputFieldProps> = ({
  id,
  label,
  tags,
  onChange,
  maxTags = 20,
  error,
}) => {
  const [inputValue, setInputValue] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const commitTag = (raw: string) => {
    const cleaned = raw.trim().toLowerCase();
    if (!cleaned) return;
    if (cleaned.length > 64) {
      setLocalError("Each tag must be 64 characters or fewer.");
      return;
    }
    if (tags.length >= maxTags) {
      setLocalError(`Maximum ${maxTags} tags allowed.`);
      return;
    }
    if (tags.includes(cleaned)) {
      setInputValue("");
      setLocalError(null);
      return;
    }
    setLocalError(null);
    onChange([...tags, cleaned]);
    setInputValue("");
  };

  const removeTag = (tagToRemove: string) => {
    setLocalError(null);
    onChange(tags.filter((t) => t !== tagToRemove));
  };

  const combinedError = localError || error;
  const errorId = combinedError ? `${id}-error` : undefined;

  return (
    <div className="space-y-2.5" aria-describedby={errorId}>
      <label htmlFor={`${id}-input`} className="block font-sans text-sm font-medium text-slate-700">
        {label}
      </label>

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2" aria-label="Selected tags">
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1.5 rounded-full bg-brand-mint/70 px-3 py-1 text-xs font-semibold text-brand-teal border border-brand-teal/15"
            >
              <span>#{tag}</span>
              <button
                type="button"
                onClick={() => removeTag(tag)}
                aria-label={`Remove tag ${tag}`}
                className="inline-flex h-5 w-5 items-center justify-center rounded-full text-brand-teal hover:bg-brand-teal hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id={`${id}-input`}
          type="text"
          value={inputValue}
          onChange={(e) => {
            const val = e.target.value;
            if (val.includes(",")) {
              const parts = val.split(",");
              parts.slice(0, -1).forEach((p) => commitTag(p));
              setInputValue(parts[parts.length - 1]);
              return;
            }
            setInputValue(val);
            if (localError) setLocalError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commitTag(inputValue);
            } else if (e.key === "Backspace" && !inputValue && tags.length > 0) {
              removeTag(tags[tags.length - 1]);
            }
          }}
          placeholder="Type a tag and press Enter (e.g. python, backend)"
          className="min-h-[44px] flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => commitTag(inputValue)}
          className="min-h-[44px] shrink-0"
        >
          <Plus className="mr-1.5 h-4 w-4" />
          Add Tag
        </Button>
      </div>

      <p className="text-xs text-slate-500">
        Normalized automatically to lowercase; duplicates are removed.
      </p>

      {combinedError && (
        <p id={errorId} role="alert" className="text-xs font-medium text-rose-600">
          {combinedError}
        </p>
      )}
    </div>
  );
};
