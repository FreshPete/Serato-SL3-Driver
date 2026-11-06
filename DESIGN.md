---
name: SL3 compatibility restoration
description: Native Windows controls for an interim prepared-session engineering window.
typography:
  title:
    fontFamily: Segoe UI
    fontSize: 21pt
    fontWeight: 600
  body:
    fontFamily: Segoe UI
    fontSize: 11pt
    fontWeight: 400
spacing:
  window-margin: 28px
  action-column-gap: 12px
components:
  action-button:
    width: 142px
    height: 38px
  secondary-action-button:
    width: 142px
    height: 34px
---

# Design System: SL3 compatibility restoration

## Overview

**Creative North Star: "Simple Windows window"**

This documents the owner's chosen native Windows direction as implemented in `src/installer/SessionWindow.cpp`. Familiar controls, plain status text and generous spacing make the prepared session understandable. The phrase above records the existing choice; it is not a newly proposed brand identity.

The current window is an interim engineering tool. The final product is one-time setup followed by launching Serato normally, as recorded in `PRODUCT.md`. This document captures current visual rules; it does not establish the session launcher as final packaging or report installation success.

**Key Characteristics:**
- Native Win32 controls with Windows-owned rendering and focus treatment.
- Two text sizes, a single content column and paired action rows.
- Inline progress with optional read-only diagnostic output.

## Colors

The operating system supplies the palette. The window background and static-label background use `GetSysColorBrush(COLOR_WINDOW)`; static-label text uses `GetSysColor(COLOR_WINDOWTEXT)`. Standard buttons, checkbox and edit control retain their native rendering with the Common Controls v6 manifest.

**The System Color Rule.** Preserve the Win32 system-color roles rather than freezing their resolved RGB values. No primary accent, tonal ramp or fixed brand palette is established. Color primitives are omitted from frontmatter because Win32 color constants are not portable CSS color values.

## Typography

**Display Font:** Segoe UI, requested directly from Windows without a project-defined fallback stack.
**Body Font:** Segoe UI, also used for labels, buttons and diagnostic output.

### Hierarchy
- **Title:** the frontmatter title token applies only to “SL3 for Serato”.
- **Body:** the body token applies to all other controls. Native font metrics determine line spacing; no custom line-height or letter-spacing is set.

Fonts use negative logical heights calculated with `MulDiv(pointSize, dpi, 72)`, with ClearType quality requested. Windows performs actual font resolution and rendering.

## Layout

Frontmatter pixel measurements are logical units at 96 DPI, scaled with `MulDiv(value, dpi, 96)`. The content width follows the client width inside equal side margins. The initial outer window is created at 780 × 500 raw pixels; the minimum tracking size is DPI-scaled from 660 × 480, or 660 × 700 with details expanded.

At 96 DPI, vertical positions and heights are: heading (24, 38), progress (78, 28), description (114, 56), wiring instructions (184, 60), primary actions (258, 38), secondary actions (310, 34), diagnostic checkbox (364, 30). Values are `(top, height)` in logical pixels. Action columns start at offsets 0 and 154 from the content left edge. No narrow-screen reflow or mobile breakpoint exists.

The diagnostic edit starts at y=406, spans the content width and has height `max(60, clientHeight−430)` in scaled units. Toggling details changes outer height by 220 scaled units. Per-monitor DPI v2 is requested; DPI changes apply the suggested bounds and recreate fonts.

## Elevation & Depth

The application adds no shadows or custom elevation. Standard Windows window chrome and native control states provide depth. Windows owns any theme-dependent effects.

## Shapes

Control bounds are rectangular. Borders, corners and focus indicators belong to the current Windows theme; no project-defined radius or border-width tokens exist.

## Components

### Buttons

Check setup is a native default push button. Start session, Session status and Recovery are standard push buttons. Native theme handling supplies hover, pressed, disabled and focus appearances.

Check setup must pass before Start session is enabled. Start can be attempted only once per prepared window. All four command buttons are disabled during a command and in preview mode. Recovery invalidates readiness. The details checkbox remains independently available.

### Diagnostic details

A native auto-checkbox reveals a multiline, read-only edit control with vertical scrolling and tab participation. Output is bounded to 65,536 bytes internally; the edit text limit is also set to 65,536. A 200 ms UI timer refreshes visible output and completion state. There is no animated progress bar or custom transition.

### Keyboard and window behavior

The message loop uses `IsDialogMessageW`, and actionable controls use `WS_TABSTOP`. Creation order is Check setup, Start session, Session status, Recovery, details, then the diagnostic edit when visible. Disabled controls are skipped by standard dialog navigation. Labels declare access keys C, S, T, R and D respectively. Check setup carries `BS_DEFPUSHBUTTON`; keyboard activation and focus rendering rely on Windows dialog behavior rather than custom handlers. These are code-level provisions, not a live keyboard validation result.

Closing while a command is active is refused and replaces the explanatory text with a wait instruction. Completion reports command results; it does not establish audible playback, installation success or clean Serato shutdown. Administrator prompts remain Windows-owned.

## Do's and Don'ts

### Do:
- **Do** preserve native controls, system-color roles and DPI-scaled layout.
- **Do** retain visible keyboard focus and explicit text for progress and results.
- **Do** identify the current window as an interim engineering tool.

### Don't:
- **Don't** invent fixed RGB brand colors, custom corner radii or browser component equivalents.
- **Don't** present a command exit as proof of playback, successful installation or clean Serato shutdown.
- **Don't** claim live keyboard, high-contrast or DPI validation from source inspection alone.
