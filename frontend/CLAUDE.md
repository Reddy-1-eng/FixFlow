@AGENTS.md

# BuildFail-SLM Frontend & UI Design Guidelines

## Interactive Web Effects with `@fiddle-digital/string-tune`
The project has `@fiddle-digital/string-tune` installed in `frontend/package.json`.

Use it for rich, responsive UI interactions and micro-animations:
- **Magnetic Buttons & Chips**: Use `string="magnetic"` on primary action buttons, preset chips, and navigation links.
- **Spotlight Cards**: Use `string="spotlight"` on diagnostic panels, result cards, and inspection boxes.
- **Tilt / Parallax**: Use `string="tilt"` on key metric boxes and overview cards.

### Next.js Client-Side Initialization
Always initialize in a client component (`"use client"`) inside `useEffect`:
```jsx
import StringTune, { StringMagnetic, StringSpotlight, StringTilt, StringParallax } from "@fiddle-digital/string-tune";

useEffect(() => {
  const tune = StringTune.getInstance();
  tune.use(StringMagnetic);
  tune.use(StringSpotlight);
  tune.use(StringTilt);
  tune.use(StringParallax);
  tune.start(60);
  return () => {
    if (typeof tune.destroy === "function") tune.destroy();
  };
}, []);
```
