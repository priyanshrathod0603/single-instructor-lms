"use client";

import React, { useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

export interface StringListEditorProps {
  id: string;
  label: string;
  description?: string;
  items: string[];
  onChange: (nextItems: string[]) => void;
  placeholder: string;
  addLabel: string;
  itemNoun: string;
  maxItems?: number;
  maxItemLength?: number;
  error?: string;
}

export const StringListEditor: React.FC<StringListEditorProps> = ({
  id,
  label,
  description,
  items,
  onChange,
  placeholder,
  addLabel,
  itemNoun,
  maxItems = 30,
  maxItemLength = 240,
  error,
}) => {
  const [draftValue, setDraftValue] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const handleAdd = () => {
    const cleaned = draftValue.trim();
    if (!cleaned) {
      setLocalError(`Enter a valid ${itemNoun.toLowerCase()} before adding.`);
      return;
    }
    if (cleaned.length > maxItemLength) {
      setLocalError(`Each ${itemNoun.toLowerCase()} must be ${maxItemLength} characters or fewer.`);
      return;
    }
    if (items.length >= maxItems) {
      setLocalError(`You can add up to ${maxItems} items.`);
      return;
    }
    if (items.some((existing) => existing.trim().toLowerCase() === cleaned.toLowerCase())) {
      setLocalError(`That ${itemNoun.toLowerCase()} is already listed.`);
      return;
    }
    setLocalError(null);
    onChange([...items, cleaned]);
    setDraftValue("");
  };

  const handleUpdateItem = (index: number, nextValue: string) => {
    setLocalError(null);
    const updated = [...items];
    updated[index] = nextValue;
    onChange(updated);
  };

  const handleMove = (index: number, direction: -1 | 1) => {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= items.length) return;
    const updated = [...items];
    const [moved] = updated.splice(index, 1);
    updated.splice(targetIndex, 0, moved);
    onChange(updated);
  };

  const handleRemove = (index: number) => {
    setLocalError(null);
    onChange(items.filter((_, idx) => idx !== index));
  };

  const combinedError = localError || error;
  const errorId = combinedError ? `${id}-error` : undefined;

  return (
    <div className="space-y-3" aria-describedby={errorId}>
      <div>
        <label htmlFor={`${id}-input`} className="block font-sans text-sm font-semibold text-slate-800">
          {label}
        </label>
        {description && (
          <p className="mt-0.5 font-sans text-xs text-slate-500">{description}</p>
        )}
      </div>

      {items.length > 0 ? (
        <ol className="space-y-2.5" aria-label={`Added ${itemNoun.toLowerCase()} items`}>
          {items.map((item, idx) => (
            <li
              key={`${id}-row-${idx}`}
              className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-slate-50/70 p-2.5 sm:flex-row sm:items-center"
            >
              <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-mint text-xs font-bold text-brand-teal">
                {idx + 1}
              </span>
              <input
                type="text"
                value={item}
                onChange={(e) => handleUpdateItem(idx, e.target.value)}
                maxLength={maxItemLength}
                aria-label={`${itemNoun} ${idx + 1}`}
                className={cn(
                  "min-h-[40px] flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-900 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal",
                  !item.trim() && "border-rose-400 focus-visible:ring-rose-500",
                )}
              />
              <div className="flex items-center justify-end gap-1 shrink-0">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={idx === 0}
                  onClick={() => handleMove(idx, -1)}
                  aria-label={`Move ${itemNoun.toLowerCase()} ${idx + 1} up`}
                  className="min-h-[40px] min-w-[40px] px-2 text-slate-600"
                >
                  <ArrowUp className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={idx === items.length - 1}
                  onClick={() => handleMove(idx, 1)}
                  aria-label={`Move ${itemNoun.toLowerCase()} ${idx + 1} down`}
                  className="min-h-[40px] min-w-[40px] px-2 text-slate-600"
                >
                  <ArrowDown className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => handleRemove(idx)}
                  aria-label={`Remove ${itemNoun.toLowerCase()} ${idx + 1}`}
                  className="min-h-[40px] min-w-[40px] px-2 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-200 bg-brand-cream/40 px-4 py-3 text-xs text-slate-500">
          No {itemNoun.toLowerCase()}s added yet. Add clear, student-facing points below.
        </div>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id={`${id}-input`}
          type="text"
          value={draftValue}
          onChange={(e) => {
            setDraftValue(e.target.value);
            if (localError) setLocalError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              handleAdd();
            }
          }}
          placeholder={placeholder}
          maxLength={maxItemLength}
          aria-invalid={!!combinedError}
          className="min-h-[44px] flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 placeholder:text-slate-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
        />
        <Button
          type="button"
          variant="outline"
          onClick={handleAdd}
          className="min-h-[44px] shrink-0 border-brand-teal/30 text-brand-teal hover:bg-brand-mint/40"
        >
          <Plus className="mr-1.5 h-4 w-4" />
          {addLabel}
        </Button>
      </div>

      {combinedError && (
        <p id={errorId} role="alert" className="text-xs font-medium text-rose-600">
          {combinedError}
        </p>
      )}
    </div>
  );
};
