# Official Visual Design System & UI/UX Governance (UI_UX_RULES)

## 1. Visual Source of Truth & Zero Design Autonomy

This document codifies the **Official Visual Design System** for the Single-Instructor LMS as supplied by the Project Owner.

**Non-Negotiable Rule**: The AI agent possesses **ZERO** design autonomy. You must never invent visual styles, adopt generic SaaS aesthetics, alter brand palettes, or modify typography scales.

All user interfaces across public marketing pages, student dashboards, staff queues, and admin builder views must strictly implement these exact specifications.

---

## 2. Design Direction: Modern Playful Minimalist

The interface must evoke:
* **Premium & Professional**: Trustworthy, refined educational experience.
* **Modern & Clean**: Generous whitespace, purposeful typography, clutter-free layouts.
* **Friendly & Engaging**: Warm, approachable tones with subtle organic energy.
* **EdTech Brand Identity**: Distinctive, proprietary authority; never looks like a generic bootstrap template.

### Anti-Patterns to Avoid (Strictly Prohibited):
* **NO** generic grey/blue SaaS dashboard templates.
* **NO** excessive gradients or iridescent visual noise.
* **NO** excessive frosted-glass glassmorphism effects.
* **NO** dark-heavy interfaces (the core palette is warm cream and clean white).
* **NO** random or unapproved hex codes.
* **NO** cramped, high-density tables or overcrowded content blocks.

---

## 3. Official Color Palette & Design Tokens

Every color in the application must be declared as a reusable design token (CSS variable / Tailwind token). Hardcoded ad-hoc hex values in component markup are strictly forbidden.

| Design Token Name | Hex Code | Semantic Role & UI Application |
| :--- | :---: | :--- |
| **`Primary Deep Teal`** | `#006B60` | Primary brand color, primary CTA buttons, active card states, navigation headers, hero split container. |
| **`Accent Coral Orange`**| `#FF8964` | Secondary CTA buttons, key headline callouts, badges, attention highlights, interactive hover accents. |
| **`Warm Cream`** | `#FFF8F5` | Primary application canvas background, hero left container, warm layout sections. |
| **`Soft Peach`** | `#FCE8E1` | Secondary card backgrounds, subtle container borders, featured module cards. |
| **`Mint`** | `#DDF3EE` | Tertiary accent, progress bars, success badges, pill indicators, gentle decorative shapes. |
| **`Pure White`** | `#FFFFFF` | Primary card surfaces, modal dialog canvas, text on Deep Teal surfaces. |
| **`Primary Text`** | `#191B24` | Primary body text, page titles, high-contrast headings, active icons. |
| **`Secondary Text`**| `#66666B` | Supporting descriptions, lesson metadata, timestamps, table sub-text. |
| **`Muted Text`** | `#929292` | Placeholder text, disabled labels, subtle borders, breadcrumb separators. |

### Visual Proportion Guidance (The 60-25-10-5 Rule)
To preserve visual harmony and brand balance, all page compositions must adhere to this color ratio:
* **60%**: Warm Cream (`#FFF8F5`) + Pure White (`#FFFFFF`) — Dominant canvas and surface breathing room.
* **25%**: Primary Deep Teal (`#006B60`) — Brand anchoring, navigation, active states, key containers.
* **10%**: Accent Coral Orange (`#FF8964`) — Targeted calls to action and visual focal points.
* **5%**: Decorative Accent Colors (Mint `#DDF3EE`, Soft Peach `#FCE8E1`).

---

## 4. Official Typography Scale

* **Primary Font Family**: **Plus Jakarta Sans**, sans-serif.
* Fallback Stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`.

| Typographic Level | Font Size | Font Weight | Line Height | Usage Context |
| :--- | :---: | :---: | :---: | :--- |
| **Hero Heading** | `52px – 60px` | `800` (Extra Bold) | `1.15` | Landing page hero headlines. |
| **Section Heading**| `36px – 42px` | `700` (Bold) | `1.2` | Major section titles, portal headings. |
| **Card Heading** | `18px – 20px` | `700` (Bold) | `1.3` | Course card titles, lesson titles, modal headers. |
| **Body Text** | `14px – 16px` | `400` (Regular) | `1.5` | Standard paragraph text, lesson descriptions, instructions. |
| **Navigation** | `14px` | `500` (Medium) | `1.4` | Top bar links, sidebar navigation items, tab labels. |
| **Small Labels** | `12px` | `500` (Medium) | `1.4` | Metadata tags, duration badges, breadcrumbs, status chips. |

---

## 5. Layout Architecture & Component Design

### 1. Hero Section Layout (Official Split Structure)
The flagship landing page hero must implement the approved two-column split structure:
* **Left Container (60% Width)**:
  * Background: `Warm Cream` (`#FFF8F5`).
  * Elements: Subtle category badge, large hero headline (with selective words highlighted in `Accent Coral Orange`), supporting description text, primary CTA button (`Primary Deep Teal`), secondary video preview CTA, and verified social proof indicators.
* **Right Container (40% Width)**:
  * Background: `Primary Deep Teal` (`#006B60`).
  * Elements: High-quality rounded student photograph framed by abstract shapes, organic curves, and subtle decorative doodles.

### 2. Card Design Standards
* **Surfaces**: `Pure White` (`#FFFFFF`) or `Soft Peach` (`#FCE8E1`).
* **Border Radius**: Generous rounded corners (`12px` to `16px`).
* **Borders & Shadows**: Subtle 1px borders (`#FCE8E1` or `#E5E5E5`); soft, diffuse box shadows (`0 4px 20px rgba(0, 0, 0, 0.04)`). Never use harsh, dark shadows.
* **Active / Highlighted Cards**: Invert surface to `Primary Deep Teal` (`#006B60`) with `Pure White` text.
* **Icons**: Thin-line, minimalist stroke icons (`1.5px` or `2px` stroke width).

### 3. Button Design Standards
* **Primary Buttons**:
  * Surface: `Primary Deep Teal` (`#006B60`).
  * Text: `Pure White` (`#FFFFFF`), `14px`, weight `600`.
  * Padding: `12px 24px`; height: `44px`; border radius: `8px` or `10px`.
  * Hover: Darken teal by 8%; subtle scale elevation (`transform: translateY(-1px)`).
* **Secondary / Action Buttons**:
  * Surface: `Accent Coral Orange` (`#FF8964`).
  * Text: `Pure White` (`#FFFFFF`), `14px`, weight `600`.
  * Hover: Darken coral by 8%.
* **Outline / Ghost Buttons**:
  * Transparent surface with 1.5px border in `Primary Deep Teal`; text in `Primary Deep Teal`.

### 4. Permitted Decorative Elements
* Subtle hand-drawn vector doodles (underlines, sparks, loops).
* Abstract organic curves and background circles in `Mint` (`#DDF3EE`) or `Soft Peach` (`#FCE8E1`).
* **Legibility Invariant**: Decorative elements must remain in background layers and must **NEVER** reduce the contrast or readability of text.

---

## 6. Design Protection & Modification Protocol

* **NEVER** independently alter brand colors, font families, font weights, padding scales, or card styles.
* If a new UI feature appears to require an element not covered by this specification, the AI agent **MUST STOP**, explain the visual need to the Project Owner, and request guidance before writing CSS or component markup.
