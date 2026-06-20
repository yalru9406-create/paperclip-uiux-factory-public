# YALRU Paperclip UI Extension Design

## 1. Product Frame

This design system covers the YALRU Agent Terminal extension mounted into Paperclip agent dashboard pages.
The surface is operational: it should feel like a compact control panel inside Paperclip, not a separate product.

## 2. Tokens

- Background: use Paperclip `hsl(var(--background))` and `hsl(var(--card))`.
- Text: use `hsl(var(--foreground))` and `hsl(var(--muted-foreground))`.
- Lines: use `hsl(var(--border))`.
- Accent: use `hsl(var(--primary))` for the primary command button only.
- Danger: use `hsl(var(--destructive))` for error text only.
- Terminal surface: use `#050505` for embedded terminal and fallback output backgrounds.
- Terminal output text: use `#d8f5dd` for fallback command stdout text.
- Panel shadow: use `0 8px 24px rgba(0,0,0,.16)` only on the outer agent terminal panel.
- Radius: use 8px for the panel, 6px for inputs and buttons.
- Spacing: use 4px multiples; panel padding is 16px, row gaps are 8px or 12px.
- Type: inherit Paperclip body font; command/output text uses `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`.

## 3. Layout

- The CLI panel mounts above the existing agent dashboard content, before Latest Run when that anchor exists.
- The panel uses one bordered surface and does not nest cards.
- Controls wrap on narrow screens and remain usable at 375px width.

## 4. Components

- Agent terminal panel: header, current agent chip, full-terminal link, embedded ttyd PTY terminal iframe.
- Command runner fallback: terminal toolbar, persistent output, command input row.
- Agent message drawer: textarea, command preview, action row, output area.
- Buttons: quiet secondary buttons for terminal utilities and status, primary buttons for command execution and wake.
- Output: monospace terminal block with bounded height and preserved whitespace.

## 5. States

- Loading: buttons disable and show a short pending label.
- Empty: ttyd attaches to the agent tmux session; fallback command runner can start the same session.
- Error: inline error text and stderr in output.
- Success: command output is shown without toast-only feedback.

## 6. Accessibility

- Textarea has a visible label inside the agent message drawer.
- Buttons are real `<button>` elements.
- Output uses `aria-live="polite"`.
- Focus styles use browser defaults plus Paperclip border contrast.

## 7. Must Not Do

- Do not expose a browser-accessible root shell.
- Real terminal panes run as the scoped Paperclip operator user, even when the tmux server is managed by root-owned services.
- Do not expose agent API key values.
- Do not introduce a separate color theme or floating decorative visuals.
- Do not wake an agent unless the operator presses the wake button.
