# {{PROJECT_NAME}} Design System

## 1. Atmosphere & Identity

Define the product feeling before building UI. The default target is a quiet, mobile-first product surface: direct decisions, clear hierarchy, and no meta documentation inside the app.

## 2. Color

| Role | Token | Light | Dark | Usage |
|---|---|---:|---:|---|
| Surface/primary | `--surface-primary` | `#FFFFFF` | `#101114` | Main background |
| Surface/secondary | `--surface-secondary` | `#F7F8FA` | `#17191D` | Secondary bands |
| Surface/elevated | `--surface-elevated` | `#FFFFFF` | `#202329` | Sheets, modals |
| Text/primary | `--text-primary` | `#191F28` | `#F4F6F8` | Main copy |
| Text/secondary | `--text-secondary` | `#6B7684` | `#A8B0BB` | Supporting text |
| Border/default | `--border-default` | `#E5E8EB` | `#343941` | Dividers |
| Accent/primary | `--accent-primary` | `#3182F6` | `#5AA2FF` | Primary CTA |
| Accent/hover | `--accent-hover` | `#1B64DA` | `#7AB6FF` | Hover/pressed |
| Status/error | `--status-error` | `#E5484D` | `#FF6B6B` | Errors |
| Status/success | `--status-success` | `#0F9F6E` | `#39D98A` | Success |

Rules:

- Use accent only for actions and focus.
- Add semantic tokens before using new colors.
- Do not use decorative purple/blue gradients as a default background.

## 3. Typography

| Level | Size | Weight | Line Height | Usage |
|---|---:|---:|---:|---|
| H1 | 28px | 700 | 1.25 | Mobile page title |
| H2 | 22px | 700 | 1.3 | Section title |
| Body | 16px | 400 | 1.55 | Default text |
| Body/sm | 14px | 400 | 1.45 | Supporting text |
| Caption | 12px | 500 | 1.35 | Metadata |

Font stack:

- Primary: system UI, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, sans-serif.
- Mono: `JetBrains Mono`, `SFMono-Regular`, monospace.

## 4. Spacing & Layout

Base unit: 4px.

| Token | Value | Usage |
|---|---:|---|
| `--space-1` | 4px | Tight inline |
| `--space-2` | 8px | Icon to label |
| `--space-3` | 12px | Field padding |
| `--space-4` | 16px | Mobile screen padding |
| `--space-5` | 20px | Section inner spacing |
| `--space-6` | 24px | Card/sheet padding |
| `--space-8` | 32px | Section separation |

Breakpoints:

- Mobile-first: 375px primary.
- Tablet: 768px.
- Desktop: 1280px.

## 5. Components

### BottomCTA

- Structure: fixed bottom region with safe-area padding.
- Variants: single CTA, double CTA, loading, disabled.
- States: default, hover/focus, pressed, loading, disabled.
- Accessibility: real button labels, focus-visible ring, keyboard trigger.
- Must not appear only inside a demo card.

### Sheet

- Structure: modal/sheet surface above dimmed background.
- States: opening, open, closing, error, loading.
- Accessibility: focus trap, escape close, labelled title.

## 6. Motion & Interaction

- Micro interactions: 100-150ms.
- Standard transitions: 200-300ms.
- Animate only transform and opacity.
- Respect `prefers-reduced-motion`.

## 7. Depth & Surface

Strategy: tonal-shift plus subtle borders.

- Bottom fixed CTA may use a subtle top shadow to separate from scroll content.
- Avoid nested cards and decorative blobs.

