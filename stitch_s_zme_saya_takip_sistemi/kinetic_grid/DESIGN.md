---
name: Kinetic Grid
colors:
  surface: '#f9f9fb'
  surface-dim: '#d9dadc'
  surface-bright: '#f9f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3f5'
  surface-container: '#eeeef0'
  surface-container-high: '#e8e8ea'
  surface-container-highest: '#e2e2e4'
  on-surface: '#1a1c1d'
  on-surface-variant: '#454652'
  inverse-surface: '#2f3132'
  inverse-on-surface: '#f0f0f2'
  outline: '#767683'
  outline-variant: '#c6c5d4'
  surface-tint: '#4c56af'
  primary: '#000666'
  on-primary: '#ffffff'
  primary-container: '#1a237e'
  on-primary-container: '#8690ee'
  inverse-primary: '#bdc2ff'
  secondary: '#705d00'
  on-secondary: '#ffffff'
  secondary-container: '#fcd400'
  on-secondary-container: '#6e5c00'
  tertiary: '#002104'
  on-tertiary: '#ffffff'
  tertiary-container: '#00390a'
  on-tertiary-container: '#4eab50'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e0e0ff'
  primary-fixed-dim: '#bdc2ff'
  on-primary-fixed: '#000767'
  on-primary-fixed-variant: '#343d96'
  secondary-fixed: '#ffe16d'
  secondary-fixed-dim: '#e9c400'
  on-secondary-fixed: '#221b00'
  on-secondary-fixed-variant: '#544600'
  tertiary-fixed: '#98f994'
  tertiary-fixed-dim: '#7ddc7a'
  on-tertiary-fixed: '#002204'
  on-tertiary-fixed-variant: '#005313'
  background: '#f9f9fb'
  on-background: '#1a1c1d'
  surface-variant: '#e2e2e4'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  data-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 8px
  container-padding-mobile: 16px
  container-padding-desktop: 32px
  gutter: 16px
  card-gap: 24px
---

## Brand & Style

The design system is engineered for a high-utility energy management platform. The brand personality is authoritative yet accessible, focusing on clarity, precision, and efficiency. It targets homeowners and facility managers who require immediate insight into complex consumption data.

The visual style is **Corporate / Modern** with a strong emphasis on **Data-First Minimalism**. It prioritizes high legibility and information density without overwhelming the user. The aesthetic utilizes ample white space to frame critical metrics, while employing a structured grid to organize diverse data points—from real-time meter readings to historical usage trends. The emotional response should be one of "controlled transparency"—giving the user a sense of absolute mastery over their energy footprint.

## Colors

The palette is designed for professional utility. **Professional Navy (#1A237E)** serves as the primary anchor, used for headers, navigation, and primary brand elements to establish trust and hierarchy. **Energy Yellow (#FFD700)** is the high-visibility accent, reserved strictly for calls to action, active states, and critical warnings.

A **Tertiary Green (#43A047)** is introduced specifically for "within-limit" status indicators and eco-friendly metrics. The background is a crisp **Clean White**, supported by a Neutral Grey scale for borders and secondary text. This high-contrast environment ensures that numerical data and progress bars remain legible under various lighting conditions.

## Typography

This design system utilizes **Inter** as the primary typeface for its exceptional legibility and neutral, systematic tone. It is used for all UI headings, body copy, and primary metrics to ensure a professional, modern feel.

To enhance the "technical" nature of the app, **JetBrains Mono** is utilized for secondary labels, meter IDs, and timestamps. This monospaced font provides a clear distinction between narrative content and raw system data. Font weights are used strategically: Bold (700) for primary metrics (kWh, costs) and Medium (500) for UI labels. Negative letter spacing is applied to large headings to maintain a tight, industrial aesthetic.

## Layout & Spacing

The layout follows a **Fluid Grid** system based on an 8px square rhythm. For desktop views, a 12-column grid is used with 24px gutters to allow for complex dashboard configurations. On mobile, the system collapses to a single-column stack with 16px side margins.

Spacing is used to group related data. Metrics within a card use tight 8px increments, while separate functional modules (e.g., "Current Usage" vs "Bill History") are separated by 32px or 48px to create clear cognitive breaks. Horizontal alignment is strictly enforced to maintain the professional, structured appearance of a technical instrument.

## Elevation & Depth

Visual hierarchy is achieved through **Tonal Layers** and **Low-Contrast Outlines**. Deep shadows are avoided to maintain a clean, "flat" professional look. 

1.  **Level 0 (Background):** The base canvas in #F5F5F7.
2.  **Level 1 (Cards):** Pure white surfaces with a subtle 1px border (#E0E0E0). These hold the primary content and data visualizations.
3.  **Level 2 (Modals/Popovers):** Elevated with a soft, diffused 15% opacity Navy shadow to indicate focus and interactivity.

Interactive elements like buttons use a subtle color shift on hover rather than an increase in physical elevation, keeping the interface grounded and stable.

## Shapes

The shape language is **Soft** and disciplined. A corner radius of 4px (0.25rem) is applied to most UI components, including input fields, buttons, and progress bar tracks. This subtle rounding removes the "sharpness" of a purely industrial tool while maintaining a professional, geometric rigor. 

Larger containers like cards may use a slightly larger 8px radius (rounded-lg) to distinguish major content areas from internal UI elements. Progress bars use fully rounded ends (caps) to signify fluid movement and "filling."

## Components

### Buttons
- **Primary:** Navy (#1A237E) background with white text. High-contrast, rectangular with 4px radius.
- **Secondary:** Yellow (#FFD700) background with Navy text. Used for "Add Funds" or "Emergency" actions.

### Cards & Progress Bars
- **Data Cards:** White background, 1px grey border. Contain a clear title, a primary metric in Inter Bold, and a supporting JetBrains Mono label.
- **Usage Bars:** A background track of light grey (#EEEEEE) with a progress fill of Primary Navy. If usage exceeds a set limit, the fill color transitions to a warning state using a secondary accent color.

### Input Fields
- Underlined or softly boxed with 1px borders. Use JetBrains Mono for numerical input to ensure alignment and prevent character jumping during typing.

### Status Icons
- Simple, stroke-based iconography (2px weight). Meter icons and shop icons should be stylized and geometric, avoiding overly decorative details to ensure they remain clear at small sizes within list items.