/**
 * Official Brand Color Tokens & Hex Values
 * Governed strictly by .ai/RULES/UI_UX_RULES.md (Zero Design Autonomy).
 */

export const BRAND_COLORS = {
  primaryTeal: "#006B60",
  primaryTealDark: "#00534B",
  accentCoral: "#FF8964",
  accentCoralDark: "#EB744F",
  warmCream: "#FFF8F5",
  softPeach: "#FCE8E1",
  mint: "#DDF3EE",
  pureWhite: "#FFFFFF",
  textPrimary: "#191B24",
  textSecondary: "#66666B",
  textMuted: "#929292",
  statusSuccess: "#00875A",
  statusWarning: "#FFAB00",
  statusError: "#DE350B",
} as const;

export type BrandColorKey = keyof typeof BRAND_COLORS;
