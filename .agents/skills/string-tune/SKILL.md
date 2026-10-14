---
name: string-tune
description: >-
  Expert guide for integrating and designing interactive UI using @fiddle-digital/string-tune.
  Provides patterns for declarative animations, parallax scrolling, magnetic cursor effects,
  spotlight cards, tilt, smooth progress, and micro-interactions in React and Next.js.
---

# StringTune Web Design & UI Skill Guide

`@fiddle-digital/string-tune` is a high-performance, modular JavaScript animation and interaction library designed for creating premium, responsive web effects via declarative HTML attributes and a modular JS engine.

---

## 1. Installation & Next.js Client-Side Setup

### Installation
```bash
npm install @fiddle-digital/string-tune
```

### Next.js (App Router) Integration Pattern
Because `StringTune` interacts directly with the DOM and window lifecycle, initialize it strictly inside client components (`"use client"`) within a `useEffect` hook:

```jsx
"use client";

import { useEffect } from "react";
import StringTune, {
  StringParallax,
  StringMagnetic,
  StringSpotlight,
  StringTilt,
  StringProgress,
} from "@fiddle-digital/string-tune";

export default function InteractiveLayout({ children }) {
  useEffect(() => {
    // 1. Get instance
    const tune = StringTune.getInstance();

    // 2. Register required modules
    tune.use(StringParallax);
    tune.use(StringMagnetic);
    tune.use(StringSpotlight);
    tune.use(StringTilt);
    tune.use(StringProgress);

    // 3. Start engine (60 FPS)
    tune.start(60);

    return () => {
      // Cleanup on unmount
      if (typeof tune.destroy === "function") {
        tune.destroy();
      }
    };
  }, []);

  return <>{children}</>;
}
```

---

## 2. Declarative Attribute Reference

StringTune uses declarative `string="<module>"` HTML attributes to bind effects directly to elements without verbose custom scripting:

### A. Magnetic Hover (`StringMagnetic`)
Draws elements toward the user's cursor on hover (perfect for CTA buttons, navigation pills, and interactive chips):
```html
<button
  className="primary-btn"
  string="magnetic"
  string-magnetic-strength="0.3"
  string-magnetic-ease="0.1"
>
  Run Analysis →
</button>
```

### B. Spotlight Glow Cards (`StringSpotlight`)
Creates modern subtle radial gradient illumination following the cursor over cards and panels:
```html
<div
  className="panel"
  string="spotlight"
  string-spotlight-color="rgba(99, 102, 241, 0.15)"
  string-spotlight-radius="260px"
>
  <h3>Root Cause Diagnosis</h3>
  <p>Detailed evidence analysis...</p>
</div>
```

### C. Parallax Elements (`StringParallax`)
Adds depth and vertical/horizontal displacement while scrolling:
```html
<div
  className="metric-card"
  string="parallax"
  string-factor="0.25"
  string-direction="vertical"
>
  <span>High Confidence</span>
</div>
```

### D. 3D Card Tilt (`StringTilt`)
Elevates dashboard metric cards with subtle responsive 3D tilt on mouseover:
```html
<div
  className="kpi-box"
  string="tilt"
  string-tilt-max="12"
  string-tilt-perspective="1000"
>
  <h4>Active Workflows</h4>
  <p>2 Workflows Monitored</p>
</div>
```

### E. Progress Indicator (`StringProgress`)
Tracks scroll progress for sticky steppers and long audit logs:
```html
<div
  className="progress-bar"
  string="progress"
  string-progress-target="#pipeline-trace"
>
  <div className="progress-fill" />
</div>
```

---

## 3. Best Practices for Dashboard & Tool UIs

1. **Subtle & Premium**: Keep magnetic strength low (`0.15`–`0.35`) and tilt angles gentle (`8deg`–`12deg`) to maintain usability while delivering a polished feel.
2. **Accessibility**: Ensure elements remain navigable via keyboard tab index and respect `prefers-reduced-motion`.
3. **SSR Safety**: Always wrap StringTune calls in client component lifecycle hooks (`useEffect`) to prevent hydration mismatches.
