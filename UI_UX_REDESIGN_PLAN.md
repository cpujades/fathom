# Talven UI/UX Redesign Plan

Last updated: 2026-05-17

## Purpose

This document is the launch-readiness plan for redesigning Talven into a modern, clean, trustworthy product across desktop, tablet, and mobile. It should stay current as implementation progresses and should be treated as the source of truth for design priorities, task status, and acceptance criteria.

## Product North Star

Talven should feel like a private briefing desk for serious long-form listeners.

The product should communicate:

- Calm intelligence, not generic AI productivity software.
- Source-backed trust, not opaque summarization.
- Fast comprehension, not transcript cleanup.
- A polished reading experience, not a document dump.
- Mobile-first usefulness, not a desktop product squeezed into a phone.

The design should be modern and clean, but still practical. Visual polish should clarify the workflow: paste a source, extract the signal, verify claims, read the brief, export or revisit it.

## Current Assessment Summary

### What works today

- The product has a coherent brand direction: quiet, editorial, private, warm.
- The signed-in app is functional and easy to understand.
- The briefing library has useful real content, thumbnails, metadata, search, sort, and actions.
- The billing flow exposes the important usage and plan information.
- The reader already has structured briefing sections and a table of contents on desktop.
- Mobile layouts are responsive and generally usable.

### What is holding the product back

- The workspace home feels empty. It is mostly a URL input instead of a useful command center.
- The landing page explains the product more than it demonstrates the product.
- The briefing reader is the core value moment, but it feels too flat and card-stacked.
- Source verification is not visible enough, despite being central to the promise.
- The visual system repeats the same cream/green card treatment across too many surfaces.
- Motion and micro-interactions are present but not memorable.
- Mobile reading is long and tiring without enough sticky navigation or progressive disclosure.
- Launch polish is incomplete: favicon, legal links, social image metadata, and accessibility details need verification.

## Design Principles

1. Reader first.
   The saved briefing page is the product. Its design quality should define the rest of the app.

2. Make trust visible.
   Source moments, timestamps, original video access, and claim provenance should be obvious.

3. Keep the workspace useful before and after submission.
   The app home should support new briefing creation, recent work, usage context, and next actions.

4. Use motion to explain transformation.
   Motion should show source-to-brief conversion, progress, state changes, and hierarchy. Avoid decoration-only animation.

5. Preserve calm density.
   Talven should feel focused and readable, but not sparse or unfinished.

6. Mobile is a primary surface.
   Long reading, account actions, billing checks, and new briefing creation must feel first-class on a phone.

7. Launch-ready means accessible and complete.
   Keyboard focus, screen reader labels, metadata, empty states, error states, legal links, and performance all matter.

## Status Legend

- Not started
- In progress
- Blocked
- Ready for review
- Done

## Workstreams

### 1. Design System Foundation

Status: In progress

Goal: Create a stronger, less repetitive UI foundation without breaking the existing Next.js and CSS module structure.

Tasks:

- [ ] Audit shared app surfaces in `apps/web/app/components/app-chrome.module.css`.
- [ ] Define a tighter color system with primary neutrals, one brand accent, semantic states, and reader-specific surfaces.
- [ ] Reduce repeated glass-card styling where elevation does not communicate hierarchy.
- [ ] Create clearer typography roles for display, section, body, metadata, timestamps, and controls.
- [ ] Add tabular numeric styling for times, balances, prices, and progress values.
- [ ] Normalize button states: hover, active, disabled, loading, focus-visible.
- [ ] Define reusable empty, loading, error, and confirmation patterns.
- [ ] Confirm reduced-motion behavior for all animated interactions.

Acceptance criteria:

- Shared styles support app, landing, reader, billing, and account surfaces.
- Buttons and inputs have visible focus states.
- Typography hierarchy is clear at 390px, 768px, 1024px, and desktop widths.
- No design system change regresses existing auth, billing, or briefing flows.

### 2. Briefing Reader Redesign

Status: In progress

Goal: Make the briefing reader feel like the premium core of the product.

Tasks:

- [x] Redesign the reader masthead with thumbnail, title, source, author, duration, generated state, and primary actions.
- [x] Convert the current summary into a stronger "brief in 30 seconds" executive panel.
- [x] Redesign key takeaways as stronger numbered claim cards instead of plain list items.
- [ ] Add visible timestamp/source affordances for important claims and quotes where data is available.
- [x] Improve the desktop table of contents with reading progress.
- [x] Add a mobile sticky reader bar with section navigation and primary actions.
- [x] Centralize live session state in a reducer so progress, markdown, stream health, and ready delivery cannot contradict each other.
- [x] Collapse processing/loading into one lifecycle panel that progressively reveals the reader when content streams.
- [x] Replace fake percentage progress with a compact four-step status timeline.
- [x] Tighten the briefing markdown contract and tolerate loose model section headings.
- [x] Warm ready briefing snapshots before library navigation to avoid fake loading flashes.
- [x] Add waiting, active, and complete lifecycle row copy with a subtle active loading signal.
- [x] Fix the live status pill so the pulse never overlaps the label.
- [x] Rename ambiguous lifecycle labels from Draft/Finalize to Write/Ready.
- [x] Keep create and live-session lifecycle rows aligned to the same four-step model.
- [x] Refresh header usage after a briefing completes so remaining time updates without a full reload.
- [x] Change ready-session reload wording from creation language to neutral opening language.
- [x] Remove the duplicate divider treatment in the Deeper read section.
- [ ] Add long-running status thresholds: 90 seconds, 3 minutes, and 5 minutes.
- [ ] Add explicit failed-state messaging for unsupported URL, no credits, provider failure, transcript failure, and summary failure.
- [ ] Collapse lower-priority sections on mobile: references, open questions, and long quote lists.
- [ ] Improve export actions so PDF and source links remain available without crowding the article.
- [ ] Improve delete confirmation placement and danger styling.
- [ ] Validate long titles, long author names, missing thumbnails, missing source links, failed sessions, and processing sessions.

Acceptance criteria:

- A user can understand the briefing value in the first viewport.
- A user can verify where important points came from.
- Mobile reader has accessible navigation without forcing a full-page scroll to reach actions.
- Desktop reader uses the right rail for navigation and utility, not just static links.
- The reader remains readable for long briefings and short briefings.

### 3. Workspace Command Center

Status: In progress

Goal: Turn `/app` from an empty input screen into a useful daily workspace.

Tasks:

- [x] Redesign the URL submission form as a primary command module.
- [x] Keep the original personalized prompt as the main workspace copy.
- [x] Keep recent work out of the workspace to preserve a focused creation flow.
- [x] Surface listening balance near the submission action without competing with the primary button.
- [ ] Add strong empty state content for first-time users.
- [ ] Improve invalid URL, unsupported source, insufficient credit, and network error states.
- [x] Add loading/progress states after submission that make the job lifecycle understandable.
- [ ] Verify the workspace on mobile as the primary creation flow.

Acceptance criteria:

- The first signed-in screen feels useful even before a user pastes a URL.
- Submission states are clear and recoverable.
- Usage balance is visible as a subtle percentage cue without dominating the workflow.
- The mobile form is comfortable to use with the on-screen keyboard.

### 4. Landing Page Redesign

Status: In progress

Goal: Make the public website demonstrate the product and convert users without feeling like a generic AI landing page.

Tasks:

- [ ] Redesign hero around the literal product promise and a strong product visual.
- [ ] Replace repeated explanatory sections with a source-to-brief transformation story.
- [ ] Add a product proof section showing realistic output: source, timestamped moments, claims, and export.
- [ ] Strengthen pricing presentation and align plan CTAs with product usage.
- [ ] Simplify FAQ and remove unnecessary repeated labels.
- [ ] Add stronger final CTA with a clear next step.
- [ ] Add legal links: privacy policy and terms of service.
- [ ] Add favicon and social sharing image metadata.
- [ ] Confirm root page performs well on mobile and does not become an exhausting scroll.

Acceptance criteria:

- The landing page shows what Talven produces, not only what it says it does.
- The hero headline stays readable and balanced across breakpoints.
- Pricing is clear on mobile and desktop.
- Footer includes required legal and contact paths.
- There are no console errors for missing assets such as `favicon.ico`.

### 5. Briefings Library Redesign

Status: In progress

Goal: Make the library easier to scan, search, revisit, and manage.

Tasks:

- [x] Improve row hierarchy: thumbnail, title, generated date, duration, author, and actions.
- [x] Add stronger search, sort, and empty-state layout.
- [ ] Consider saved filters or quick filters: recent, long, source, author, processing, failed.
- [ ] Improve destructive remove flow with inline confirmation.
- [x] Add mobile-specific row actions that do not crowd the title.
- [ ] Add skeleton loading that matches library row shapes.

Acceptance criteria:

- A user can scan 12 or more briefings without the page feeling visually noisy.
- Search and sort are easy to find and use on mobile.
- Remove actions are safe and hard to trigger accidentally.
- Empty and loading states feel composed.

### 6. Billing And Account Polish

Status: In progress

Goal: Make billing trustworthy, readable, and mobile-friendly without overdesigning it.

Tasks:

- [ ] Redesign usage balance with clearer plan, monthly allowance, rollover, and pack reserve distinctions.
- [ ] Improve plan cards so recommended choices are clear without relying on small badges.
- [ ] Improve pack and billing history presentation.
- [ ] Clarify refund eligibility and confirmation states.
- [ ] Polish account settings as a small but complete identity surface.
- [ ] Ensure all billing actions have loading, error, success, and disabled states.

Acceptance criteria:

- A user can understand how much time they have and when it expires.
- Upgrade and pack purchase actions are visually distinct and safe.
- Billing is fully usable on mobile.
- Account settings do not feel like an unfinished utility page.

### 7. Navigation And App Chrome

Status: Not started

Goal: Make navigation feel intentional across signed-in app surfaces.

Tasks:

- [ ] Reassess top navigation layout on desktop, tablet, and mobile.
- [ ] Improve active nav styling and page context.
- [ ] Decide whether mobile needs bottom navigation, top tabs, or a compact command/header pattern.
- [ ] Improve account menu placement and touch targets.
- [ ] Ensure account and billing paths never feel like dead ends.

Acceptance criteria:

- Users always know where they are.
- Primary navigation remains usable on 390px mobile screens.
- Touch targets meet accessibility expectations.
- Account menu content is readable and not cramped.

### 8. Accessibility And Inclusive UX

Status: Not started

Goal: Make launch readiness apply to all users, not only visual polish.

Tasks:

- [x] Add skip-to-content link.
- [ ] Verify heading order on landing, app, billing, library, account, and reader.
- [ ] Verify keyboard navigation for menus, tabs, accordions, delete confirmations, and billing actions.
- [x] Verify visible focus indicators on all interactive elements.
- [ ] Verify color contrast for text, muted labels, buttons, danger actions, and badges.
- [ ] Verify form labels, error messages, and accessible descriptions.
- [ ] Verify reduced-motion behavior.
- [ ] Test with mobile viewport and real-device observations.

Acceptance criteria:

- Keyboard users can complete primary flows.
- Screen reader structure is sensible.
- Error messages are specific and announced near the relevant control.
- Motion does not block users who prefer reduced motion.

### 9. Launch Polish

Status: In progress

Goal: Close the small gaps that make a product feel unfinished.

Tasks:

- [x] Add favicon assets and confirm no missing favicon console errors.
- [x] Add Open Graph image and Twitter image metadata.
- [x] Add privacy policy and terms links.
- [ ] Verify custom 404 and not-found behavior.
- [ ] Confirm no dead links or placeholder links remain.
- [ ] Confirm no secrets or internal-only debug content appears in the UI.
- [ ] Confirm production env behavior does not rely on localhost defaults.
- [ ] Verify all pages have appropriate titles and descriptions.

Acceptance criteria:

- No missing asset errors in the browser console.
- Public pages are shareable with correct metadata.
- Legal and contact paths are present.
- The app feels complete in edge cases, not only happy paths.

## Execution Roadmap

This is the current working sequence. Use it to avoid duplicated work and to keep the next implementation step obvious.

### Phase A: Session State Reliability

Status: Done

Completed:

- [x] Centralized briefing session UI state in a reducer.
- [x] Prevented stale snapshots from moving progress backward.
- [x] Prevented empty snapshots from erasing streamed markdown.
- [x] Kept ready sessions without markdown in a delivery state instead of opening an empty reader.
- [x] Added reducer tests for regressions.

### Phase B: One Lifecycle Screen

Status: In progress

Completed:

- [x] Collapsed separate processing/loading cards into one session lifecycle surface.
- [x] Replaced fake percentage progress with a four-step timeline.
- [x] Aligned `/app/briefings/new` and session processing visuals so they feel like one flow.
- [x] Removed robotic explanatory copy from the lifecycle rows.
- [x] Added waiting, active, and complete row states.
- [x] Added subtle active loading signal.
- [x] Fixed live status pill overlap.
- [x] Warm-prefetched ready sessions from the library before navigation.
- [x] Handled network-level session snapshot failures without unhandled frontend promise rejections.
- [x] Tightened the summary prompt and bumped cache key to `briefing-v4`.
- [x] Made the reader parser tolerate loose model section headings.
- [x] Unified creation and live-session lifecycles around Check source, Transcribe, Write, Ready.
- [x] Added smoother lifecycle/card transitions.
- [x] Refreshed usage after session completion.
- [x] Broadcast successful usage updates across open app tabs.
- [x] Avoided "creating from scratch" wording when a saved briefing is opened or reloaded.
- [x] Aligned the creation loading card with the live session card position on desktop and mobile.

Still missing:

- [ ] Re-verify the lifecycle transition on a real new briefing from submit to streamed content after the position and four-step alignment.
- [ ] Verify the reused-ready path feels instant from library and creation flow.
- [ ] Verify missing thumbnail, unknown title, unsupported URL, no credits, and provider failure states.
- [ ] Tune mobile spacing after real-device testing.

### Phase C: Better User-Facing Status

Status: In progress

Goal: Make users trust long-running jobs without exposing implementation noise.

Tasks:

- [x] Replace remaining generic status copy with stage-specific, short, confident language.
- [x] Show source-of-truth stage names: checking source, transcribing, writing, saving.
- [x] Add long-running thresholds:
  - [x] After 30 seconds: show a calm "still working" message without implying a problem.
  - [x] After 60 seconds: explain that longer sources can take a minute or two before writing starts.
  - [x] After 2 minutes: note that the job is taking a little longer than usual.
  - [x] After 5 minutes: tell the user they can leave and return from the library.
  - [x] After 10 minutes: make the state more explicit that it may be stuck and can be retried later.
- [x] Show in-progress and failed sessions in the Briefings library with compact status pills and a direct progress/review action.
- [x] Add clear failed states:
  - [x] Unsupported URL or unusable source.
  - [x] No credits or insufficient time.
  - [x] Provider or retry failure.
  - [x] Transcript failure.
  - [x] Summary failure.
- [x] Make reconnect states calm and non-alarming.

Acceptance criteria:

- Users always know whether Talven is checking, listening, writing, finalizing, ready, or failed.
- Long waits feel accounted for, not broken.
- Failed states are specific enough to guide the next action.

### Phase D: Backend Observability

Status: In progress

Goal: Make the product debuggable during real use.

Tasks:

- [x] Add structured logs for every major backend stage.
- [x] Include elapsed time, provider/model, job/session id, user id, stage, and safe error code.
- [x] Log first streamed chunk from OpenRouter without logging generated content.
- [x] Log first markdown persisted to Supabase.
- [x] Log fallback summarizer usage.
- [x] Log final markdown length and flush count.
- [x] Add clearer backend error codes for frontend display.
- [x] Keep routine no-op maintenance logs out of normal INFO output.
- [x] Move small observability helpers out of the runner.
- [x] Keep the worker runner focused on job claiming, retry, and maintenance; move transcript and summary execution into orchestration modules.
- [ ] Verify logs during one fresh end-to-end briefing and one cached briefing.

Acceptance criteria:

- Given a failed or slow session id, the backend logs explain where time was spent and what failed.
- Provider/model details are visible without logging secrets.
- Frontend errors can map to stable backend error codes.
- Normal terminal output remains readable during idle periods and routine successful jobs.

### Phase E: Admin/Developer Visibility

Status: In progress

Goal: Debug real user reports quickly without manually piecing together logs.

Tasks:

- [x] Add a local/debug job timeline view or CLI command.
- [x] Keep the timeline command in the diagnostics module: `PYTHONPATH=apps/backend python -m fathom.application.diagnostics.job_timeline <session_id>`.
- [x] Model diagnostic snapshots with Pydantic schemas instead of raw dictionaries.
- [x] Given a session/job id, show created, claimed, source fetched, transcription started/completed, summary started, first markdown, completed/failed.
- [x] Pull from sparse persisted job events, with persisted row checkpoints as a fallback.
- [x] Keep this local/admin-only and out of the user-facing app.
- [ ] Verify the command against one fresh briefing, one cached briefing, and one failed/unsupported source.

Acceptance criteria:

- A session can be diagnosed quickly from one command or internal view.
- The timeline is useful for slow jobs, failed jobs, and provider debugging.
- The timeline adds durable debugging value without increasing normal terminal noise.

### Phase F: Polish And Launch Hardening

Status: Not started

Goal: Finish product readiness after the core generation and reading flows are stable.

Tasks:

- [ ] Mobile lifecycle screen polish.
- [ ] Slow-network and reconnect testing.
- [ ] Error state review.
- [ ] Empty states.
- [ ] Billing/account consistency.
- [ ] Landing page product proof.
- [ ] Cross-device QA across the device matrix below.
- [ ] Final console, accessibility, and build validation.

Acceptance criteria:

- The app feels coherent from landing page to account/billing to reader.
- Mobile and desktop both feel intentionally designed.
- Edge states feel finished enough for launch.

## Remaining Product Surfaces

### Briefing Creation Flow

Status: In progress

Next work:

- [ ] Verify the create-to-session transition is visually seamless.
- [x] Keep creation and session lifecycle components visually aligned.
- [x] Keep creation and session loading cards in the same viewport position.
- [ ] Improve creation errors for invalid URL, unsupported source, no credits, and network failure.
- [ ] Test mobile keyboard behavior and touch targets.

### Billing And Account Cleanup

Status: Not started

Next work:

- [ ] Make quota, checkout, empty states, and plan states feel launch-ready.
- [ ] Clarify subscription time versus pack time.
- [ ] Align account and billing surfaces with the redesigned app chrome.
- [ ] Verify loading, disabled, success, and error states.

### Landing Page And Product Proof

Status: Not started

Next work:

- [ ] Bring the public site up to the same design quality as the app.
- [ ] Show actual output structure instead of generic AI claims.
- [ ] Add product proof: source, generated briefing, takeaways, reader, export.
- [ ] Ensure the landing page is fast, mobile-readable, and not overexplained.

## Device QA Matrix

Primary breakpoints:

- Mobile small: 360px wide
- Mobile standard: 390px wide
- Mobile large: 430px wide
- Tablet: 768px wide
- Small laptop: 1024px wide
- Desktop: 1440px wide
- Wide desktop: 1920px wide

Core flows to test at each relevant breakpoint:

- Public landing page.
- Sign in and sign up.
- Create new briefing from `/app`.
- Processing or loading briefing state.
- Saved briefing reader.
- Library search, sort, open, remove.
- Billing usage, plan upgrade, packs, refund states.
- Account settings.

Real-device notes:

- Use Browser viewport testing as the repeatable baseline.
- Use the mirrored phone through scrcpy for human-observed touch behavior, mobile browser chrome, keyboard behavior, scroll feel, and physical readability.
- Record any real-device issues back into this document under the relevant workstream.

## Quality Gates Before Launch

- [ ] No missing asset console errors.
- [ ] No horizontal overflow at mobile widths.
- [ ] All primary flows work with keyboard navigation.
- [ ] All forms have visible labels and inline errors.
- [ ] All destructive actions require confirmation.
- [ ] All loading states are understandable.
- [ ] All empty states include a useful next action.
- [ ] Reader is comfortable on mobile for long briefings.
- [ ] Landing page demonstrates the actual product output.
- [ ] Pricing and billing are clear on mobile.
- [ ] Privacy, terms, contact, favicon, and social metadata are present.
- [ ] Frontend lint passes.
- [ ] Frontend typecheck passes.
- [ ] Frontend build passes.

## Decision Log

Use this section to record intentional design decisions.

| Date | Decision | Reason | Owner |
| --- | --- | --- | --- |
| 2026-05-15 | Start redesign with a root-level tracker. | The redesign spans multiple surfaces and must remain launch-focused. | Codex |
| 2026-05-15 | Prioritize the briefing reader before the landing page. | The reader is the core product moment and should define the design system. | Codex |
| 2026-05-15 | Use Browser viewport testing as the repeatable baseline, with scrcpy as real-device observation support. | Browser testing is reproducible; scrcpy is valuable for touch, keyboard, and physical readability checks. | Codex |

## Open Questions

- Should the reader include explicit confidence, source coverage, or citation quality indicators?
- Should the workspace home prioritize recent briefings or the new briefing command?
- Should mobile navigation remain top-tab based or move toward a bottom navigation pattern?
- What legal pages are required before launch: privacy, terms, refund policy, cookie policy?
- Should the landing page include real sample screenshots from the product or designed product mockups based on live components?
