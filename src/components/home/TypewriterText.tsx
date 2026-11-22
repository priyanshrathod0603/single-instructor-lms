"use client";

import React, { useState, useEffect } from "react";

export interface TypewriterTextProps {
  phrases?: string[];
  typingSpeed?: number;
  deletingSpeed?: number;
  pauseDuration?: number;
  className?: string;
}

export const DEFAULT_HERO_PHRASES = [
  "Distributed Systems",
  "Backend Architecture",
  "Production APIs",
  "Enterprise Security",
];

export const TypewriterText: React.FC<TypewriterTextProps> = ({
  phrases = DEFAULT_HERO_PHRASES,
  typingSpeed = 75,
  deletingSpeed = 40,
  pauseDuration = 1800,
  className = "",
}) => {
  // Deterministic initial state: identical on server and client
  const [displayedText, setDisplayedText] = useState("");

  useEffect(() => {
    // Respect user's explicit OS/browser reduced-motion accessibility preference
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mediaQuery.matches) {
      setDisplayedText(phrases[0] || "Distributed Systems");
      return;
    }

    let isCancelled = false;
    let phraseIdx = 0;
    let charIdx = 0;
    let deleting = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    const tick = () => {
      if (isCancelled) return;

      const currentPhrase = phrases[phraseIdx] || phrases[0] || "";

      if (!deleting) {
        // Typing phase: append next character
        charIdx++;
        setDisplayedText(currentPhrase.substring(0, charIdx));

        if (charIdx >= currentPhrase.length) {
          // Completed phrase: pause before deleting
          deleting = true;
          timeoutId = setTimeout(tick, pauseDuration);
        } else {
          timeoutId = setTimeout(tick, typingSpeed);
        }
      } else {
        // Deleting phase: remove character
        charIdx--;
        setDisplayedText(currentPhrase.substring(0, charIdx));

        if (charIdx <= 0) {
          // Finished deleting: pause briefly, transition to next phrase
          deleting = false;
          phraseIdx = (phraseIdx + 1) % phrases.length;
          timeoutId = setTimeout(tick, 300);
        } else {
          timeoutId = setTimeout(tick, deletingSpeed);
        }
      }
    };

    // Schedule first typing tick post-hydration
    timeoutId = setTimeout(tick, typingSpeed);

    return () => {
      isCancelled = true;
      clearTimeout(timeoutId);
    };
  }, [phrases, typingSpeed, deletingSpeed, pauseDuration]);

  return (
    <span
      className={`inline text-primary-teal font-extrabold tracking-tight break-words ${className}`}
      aria-live="polite"
      aria-atomic="true"
    >
      <span>{displayedText}</span>
      <span
        className="ml-1 inline-block h-[0.85em] w-[3px] rounded-full bg-accent-coral align-baseline animate-cursor-blink"
        aria-hidden="true"
      />
    </span>
  );
};
