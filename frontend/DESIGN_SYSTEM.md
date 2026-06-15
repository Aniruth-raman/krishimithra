# KrishiMitra 2026 AI Interface Design System

## Identity

KrishiMitra uses a calm AI operating-system language: dark-first, spacious, premium, and productivity-oriented. The interface combines a workspace sidebar, centered readable chat, floating composer, contextual action chips, and responsive mobile-first controls.

## Tokens

- Backgrounds: `#0B0F17`, `#121826`, `#171F2E`
- Dark surfaces: `#1D2636`, `#232E42`
- Light backgrounds: `#FAFBFC`, `#FFFFFF`, `#F3F6FA`
- Primary accents: electric blue `#4F8CFF`, violet `#8A63FF`
- Secondary accents: cyan `#33D6FF`, emerald `#3DDC97`
- Text dark mode: primary `#F8FAFC`, secondary `#AAB4C5`, muted `#718096`
- Text light mode: primary `#0F172A`, secondary `#475569`
- Radius: 12px small, 16px medium, 24px large
- Motion: 150ms fast interactions, 220ms default transitions
- Grid: 8pt spacing rhythm through 8, 16, 24, 32px clusters

## Core Components

- AI workspace sidebar with switcher, search, pinned chats, projects, and theme toggle
- Centered chat stream with sticky date separator and readable max width
- AI and user bubbles with distinct but restrained treatment
- Floating composer with add menu, voice, file, image, screen capture, and send controls
- Agent and tool pills for workspace-level controls
- Live intelligence cards for weather, disease hotspots, and action suggestions
- Landing/auth page with product preview, trust pills, and adaptive theme controls

## Interaction States

- Hover: 1px lift, accent border, subtle gradient fill
- Focus: 4px blue focus ring with high contrast
- Streaming/loading: existing thinking state and voice pulse states
- Voice: idle, listening, transcribing, thinking, speaking
- Disabled: reduced opacity with preserved layout dimensions

## Responsive Behavior

- Desktop: persistent workspace sidebar and wide centered content
- Tablet: sidebar remains top-level but dense groups collapse
- Mobile: single-column content, hidden secondary composer tools, full-width send action
