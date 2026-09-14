# IdeaFlow UI/UX Motion Enhancement Plan

## Goal

Make IdeaFlow feel polished and continuous without moving, reordering, or
rewriting page content. Business workflows, forms, routes, data fetching,
Socket.IO, and server-rendered page scripts must continue to behave exactly as
before.

## Design direction

- Quiet, confident motion rather than decorative or playful animation.
- Preserve IdeaFlow's existing gold, white, and slate visual language.
- Keep navigation chrome visually anchored while page content transitions.
- Give immediate feedback for navigation, buttons, cards, and form focus.
- Respect reduced-motion preferences and older browsers.

## Implementation

1. Add a shared motion stylesheet with reusable timing and easing tokens.
2. Use native cross-document View Transitions for same-origin page navigation.
   This retains full page loads so page-specific scripts initialize normally.
3. Add a thin navigation progress indicator for immediate click feedback.
4. Add restrained entrance, hover, press, focus, modal, and navigation motion.
5. Load the motion layer from both the authenticated and public/auth layouts.
6. Disable non-essential movement under `prefers-reduced-motion`.
7. Add regression tests for asset wiring, accessibility, and safe navigation.

## Invariants

- No page element is moved or reordered.
- No endpoint, form action, permission, database operation, or API call changes.
- No client-side HTML swapping is introduced.
- Modified-click, download, external, hash, and new-tab links retain native behavior.
- Unsupported browsers keep normal navigation with no functional degradation.

## Acceptance checks

- Representative admin, staff, customer, login, and error pages render normally.
- Navigation shows immediate feedback and transitions without a white flash in
  supported browsers.
- Page-specific JavaScript, Socket.IO, forms, modals, and browser history work.
- Keyboard focus remains visible.
- Reduced-motion mode removes animation and smooth scrolling.
- Full automated test suite passes.
