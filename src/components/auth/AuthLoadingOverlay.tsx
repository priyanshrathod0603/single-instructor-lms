"use client";

import React from "react";
import { motion, AnimatePresence, useReducedMotion, type Variants } from "motion/react";
import { GraduationCap } from "lucide-react";

export interface AuthLoadingOverlayProps {
  /** Whether the loading state/overlay is active */
  isOpen: boolean;
  /** Primary status indicator text (e.g. "Connecting securely…") */
  statusMessage?: string;
  /** Optional secondary context message */
  subMessage?: string;
  /** Whether to render as fixed full-screen backdrop or embedded inline */
  isFullScreen?: boolean;
  /** Optional custom class name for the wrapper */
  className?: string;
}

export const AuthLoadingOverlay: React.FC<AuthLoadingOverlayProps> = ({
  isOpen,
  statusMessage = "Verifying your credentials…",
  subMessage,
  isFullScreen = true,
  className = "",
}) => {
  const shouldReduceMotion = useReducedMotion();

  const backdropVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { duration: shouldReduceMotion ? 0.1 : 0.2 },
    },
    exit: {
      opacity: 0,
      transition: { duration: shouldReduceMotion ? 0.1 : 0.2 },
    },
  };

  const cardVariants: Variants = {
    hidden: {
      opacity: 0,
      scale: shouldReduceMotion ? 1 : 0.96,
    },
    visible: {
      opacity: 1,
      scale: 1,
      transition: {
        duration: shouldReduceMotion ? 0.1 : 0.25,
        ease: "easeOut",
      },
    },
    exit: {
      opacity: 0,
      scale: shouldReduceMotion ? 1 : 0.96,
      transition: {
        duration: shouldReduceMotion ? 0.1 : 0.2,
      },
    },
  };

  const content = (
    <motion.div
      variants={cardVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-busy="true"
      className={`relative w-full max-w-[340px] sm:max-w-sm rounded-2xl border border-soft-peach bg-white/95 p-6 sm:p-8 text-center shadow-xl backdrop-blur-md ${className}`}
    >
      {/* Animated Brand Logo & Spinner */}
      <div className="relative mx-auto mb-5 flex h-16 w-16 items-center justify-center">
        {/* Outer Rotating Accent Ring */}
        <motion.div
          animate={shouldReduceMotion ? undefined : { rotate: 360 }}
          transition={
            shouldReduceMotion
              ? undefined
              : { duration: 1.5, repeat: Infinity, ease: "linear" }
          }
          className="absolute inset-0 rounded-full border-2 border-accent-mint/40 border-t-accent-coral border-r-primary-teal"
        />

        {/* Inner Pulsing Brand Icon Container */}
        <motion.div
          animate={
            shouldReduceMotion
              ? undefined
              : { scale: [1, 1.04, 1] }
          }
          transition={
            shouldReduceMotion
              ? undefined
              : { duration: 2, repeat: Infinity, ease: "easeInOut" }
          }
          className="relative flex h-12 w-12 items-center justify-center rounded-xl bg-primary-teal text-white shadow-md"
        >
          <GraduationCap className="h-6 w-6 text-white" />
        </motion.div>
      </div>

      {/* Brand Watermark Title */}
      <div className="mb-2 select-none">
        <span className="font-heading text-xs font-bold uppercase tracking-widest text-slate-400">
          Instructor<span className="text-primary-teal">LMS</span>
        </span>
      </div>

      {/* Dynamic Accessible Status Message */}
      <div className="min-h-[28px] flex items-center justify-center overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.p
            key={statusMessage}
            initial={{ opacity: 0, y: shouldReduceMotion ? 0 : 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: shouldReduceMotion ? 0 : -4 }}
            transition={{ duration: shouldReduceMotion ? 0.1 : 0.2 }}
            className="font-heading text-base font-bold text-slate-900 leading-snug"
          >
            {statusMessage}
          </motion.p>
        </AnimatePresence>
      </div>

      {/* Optional Sub-Message */}
      {subMessage && (
        <p className="mt-1.5 font-sans text-xs text-slate-500 leading-relaxed">
          {subMessage}
        </p>
      )}

      {/* Subtle indicator dots */}
      <div className="mt-4 flex items-center justify-center gap-1.5" aria-hidden="true">
        <motion.span
          animate={shouldReduceMotion ? undefined : { opacity: [0.3, 1, 0.3] }}
          transition={shouldReduceMotion ? undefined : { duration: 1.2, repeat: Infinity, delay: 0 }}
          className="h-1.5 w-1.5 rounded-full bg-primary-teal"
        />
        <motion.span
          animate={shouldReduceMotion ? undefined : { opacity: [0.3, 1, 0.3] }}
          transition={shouldReduceMotion ? undefined : { duration: 1.2, repeat: Infinity, delay: 0.2 }}
          className="h-1.5 w-1.5 rounded-full bg-accent-coral"
        />
        <motion.span
          animate={shouldReduceMotion ? undefined : { opacity: [0.3, 1, 0.3] }}
          transition={shouldReduceMotion ? undefined : { duration: 1.2, repeat: Infinity, delay: 0.4 }}
          className="h-1.5 w-1.5 rounded-full bg-primary-teal"
        />
      </div>
    </motion.div>
  );

  return (
    <AnimatePresence>
      {isOpen && (
        isFullScreen ? (
          <motion.div
            variants={backdropVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-4 backdrop-blur-[2px]"
          >
            {content}
          </motion.div>
        ) : (
          content
        )
      )}
    </AnimatePresence>
  );
};
