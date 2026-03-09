# Frontend Design Blueprint

## 1. Objective
Build a high-clarity, recruiter-first frontend using only HTML, CSS, and JavaScript, integrated with the local API.

The UI should make it easy to:
- browse requisitions quickly
- interact with the recruitment agent in context
- inspect candidates, resumes, and match evidence without losing flow

## 2. Core UX Principles
- Fast orientation: user should understand what is open, what needs action, and what is completed in under 5 seconds.
- Progressive detail: show summaries first, then deep evidence only when needed.
- Action-driven states: each screen should make the next best action obvious.
- Grounded trust: every score/explanation links to real data fields and resume evidence.
- Minimal context switching: keep requisitions, chat, candidates, and resume details in one coordinated workspace.

## 3. App Shell Layout
Three-column desktop layout with sticky headers and independent scroll areas.

### Left Column: Requisition Navigator
Purpose: quick selection and status tracking.

Sections:
- Recruiter header
- Filter bar:
  - Status filter (Open, Clarification Needed, In Progress, Completed)
  - Search requisition by title/id
- Requisition list cards:
  - Req ID and title
  - Department/location
  - Status badge
  - Candidate count preview
  - Last updated timestamp

Interaction:
- Click requisition card sets active context for the whole app.
- Active requisition card has stronger visual emphasis and left accent bar.

### Right Column: Agent Interaction Panel
Purpose: recruiter-agent collaboration.

Sections:
- Chat history stream
- Clarification question cards (when required)
- Quick reply chips (Yes/No/Remote/Hybrid/Bachelor/Master/PhD)
- Message composer + submit
- Action buttons:
  - Run Search
  - Re-rank
  - Reset Clarifications

Interaction:
- Agent prompts are linked to target fields.
- Clarification responses update state and trigger search refresh.

### Center Column: Primary Work Area (Tabbed)
Purpose: detailed inspection and decision-making.

Tabs:
- Requisition
- Candidates
- Candidate Profile
- Resume Viewer
- Audit Trail

Tab behavior:
- Requisition tab opens by default.
- Candidate click auto-opens Candidate Profile tab.
- Resume link auto-opens Resume Viewer tab.

## 4. Center Tab Specifications

### 4.1 Requisition Tab
Displays structured requirement schema and current confidence.

Blocks:
- Role summary
- Must-have skills / Nice-to-have skills
- Education and experience constraints
- Work constraints
- Confidence + Missing fields panel

Controls:
- Edit overrides (inline)
- Save overrides
- Trigger clarification loop

### 4.2 Candidates Tab
Main decision board for shortlist.

Layout:
- Table + cards hybrid
- Columns:
  - Rank
  - Candidate
  - Current title
  - Match score
  - Skill coverage
  - Education match
  - Flags/Risks
  - Actions

Actions per row:
- View profile
- Open resume
- Add note
- Mark shortlist / reject

Sorting and filtering:
- score desc (default)
- experience years
- location
- title type

### 4.3 Candidate Profile Tab
Detailed candidate evidence.

Sections:
- Overview strip (name, title, score, status)
- Skill evidence list
- Experience timeline
- Education block
- Gap analysis
- Suggested interview questions

### 4.4 Resume Viewer Tab
Resume context and extracted text side-by-side.

Split view:
- Left: embedded PDF frame
- Right: extracted summary/text snippets with highlighted evidence terms

Controls:
- Next/Prev candidate
- Highlight matched terms
- Download resume

### 4.5 Audit Trail Tab
Traceability and compliance.

Shows:
- Requisition ingest event
- Parsed requirements versions
- Clarification Q/A history
- Search plan snapshots
- Result set versions
- Feedback actions

## 5. Visual Design Direction
A clean, high-contrast "operations console" style.

### Typography
- Heading font: `Space Grotesk`, fallback `Segoe UI`, `Arial`, sans-serif
- Body font: `Source Sans 3`, fallback `Segoe UI`, `Arial`, sans-serif
- Monospace for IDs/status payloads: `JetBrains Mono`, fallback `Consolas`, monospace

### Color System (no purple bias)
Define CSS variables:
- `--bg-main: #f3f6f8`
- `--bg-panel: #ffffff`
- `--bg-elevated: #eef3f6`
- `--text-primary: #13212b`
- `--text-muted: #5d6f7c`
- `--accent: #0b7285` (teal)
- `--accent-strong: #075985`
- `--success: #2b9348`
- `--warning: #d98e04`
- `--danger: #b42318`
- `--border: #d8e1e8`

Status badge colors:
- Open: teal
- Clarification Needed: amber
- In Progress: blue
- Completed: green
- Blocked/Error: red

### Background Treatment
- Subtle gradient base + faint grid texture for workspace depth.
- Cards use soft shadows and clear borders for separability.

### Motion
- Page load: staggered fade-up for columns.
- Tab switch: 120ms slide/fade.
- Requisition selection: subtle highlight sweep.
- Avoid noisy micro-animations.

## 6. Responsive Behavior

### Desktop (>=1200px)
- 3-column layout fixed ratio: 22% | 50% | 28%

### Tablet (768-1199px)
- Left column collapses into drawer
- Center and right remain side by side

### Mobile (<768px)
- Single-column stack with bottom nav:
  - Requisitions
  - Work Tabs
  - Agent
- Resume viewer opens full-screen modal

## 7. Data Contracts to Existing APIs

Use existing local endpoints:
- `GET /ats/requisitions`
- `GET /ats/requisitions/{id}/applications`
- `GET /ats/candidates/{id}`
- `POST /requisition/ingest`
- `POST /requisition/{id}/clarify`
- `POST /search`
- `GET /candidate/{id}`

Frontend state model (client-side JS):
- `selectedRequisition`
- `sessionId`
- `currentRequirements`
- `clarificationQuestions`
- `rankedCandidates`
- `selectedCandidate`
- `activeTab`

## 8. Suggested File Structure (HTML/CSS/JS only)
- `frontend/index.html`
- `frontend/styles.css`
- `frontend/app.js`
- `frontend/components/`
  - `requisition-list.js`
  - `agent-panel.js`
  - `tabs.js`
  - `candidates-table.js`
  - `resume-viewer.js`
- `frontend/assets/`

If strict single-file is preferred initially:
- `frontend/index.html` with linked `styles.css` and `app.js`

## 9. Build Steps (Implementation Plan)

### Step A: Shell + Static Layout
- Build 3-column responsive shell in HTML/CSS.
- Add tab container and placeholder content.
- Implement design tokens and typography.

### Step B: Requisition List + Selection
- Wire `GET /ats/requisitions`.
- Render list cards + status badges.
- Set active requisition and sync center/right context.

### Step C: Agent Panel + Clarification Loop
- Add chat-like history UI.
- Wire `POST /requisition/ingest`.
- Show clarification cards and collect answers.
- Wire `POST /requisition/{id}/clarify`.

### Step D: Candidate Search + Table
- Wire `POST /search`.
- Render ranked candidates in sortable table/card view.
- Add row actions to open profile/resume tabs.

### Step E: Candidate Profile + Resume Viewer
- Wire `GET /candidate/{id}` and `GET /ats/candidates/{id}`.
- Render profile evidence.
- Embed PDF using configured resume path.

### Step F: Audit + Session UX Polish
- Add timeline panel for status transitions.
- Add loading/empty/error states.
- Add keyboard navigation and aria labels.

### Step G: Final UX Hardening
- Improve spacing/visual hierarchy.
- Add light animation polish.
- Verify mobile and tablet breakpoints.

## 10. Acceptance Criteria for Frontend
- Requisition list loads and selecting one updates main context.
- Ingest and clarification cycle is fully interactive.
- Search shows ranked candidates and top evidence.
- Candidate detail and resume can be opened without page reload.
- All API errors show clear inline messages.
- Layout works on desktop/tablet/mobile.
- Recruiter can complete a shortlist flow without leaving the app shell.
