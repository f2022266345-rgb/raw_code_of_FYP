web application/stitch/projects/433007316358808282/screens/9dc83247e62d4f81977c582ce97300fe
# Product Requirements Document (PRD): FYP Agentic AI Platform Redesign

## 1. Project Overview
**Project Name:** FYP Agentic AI Guidance Platform  
**Status:** Design Phase  
**Product Manager:** Hafiz Abdullah Amjad 

The project involves a complete frontend overhaul of an AI-driven platform designed to assist Final Year Project (FYP) students. The platform utilizes specialized AI agents to guide students through the academic lifecycle—from initial topic selection to final presentation. The redesign aims to transition from a basic functional tool to a premium, "next-gen" SaaS experience that balances academic professionalism with cutting-edge AI capabilities.

## 2. Objectives &amp; Success Metrics
### 2.1 Objectives
*   **Establish Brand Identity:** Create a visual language that communicates trust, intelligence, and productivity.
*   **Optimize Conversion:** Redesign the landing page and onboarding flow to maximize sign-ups and user retention.
*   **Enhance UX/UI:** Improve information architecture and task management within the core dashboard.
*   **Agent Integration:** Provide a seamless interface for interacting with various AI agents (Topic, Proposal, Dev, etc.).

### 2.2 Success Metrics
*   **Onboarding Completion Rate:** Goal > 85% completion of the 3-phase setup.
*   **User Engagement:** Increase the number of agent interactions per session.
*   **Conversion Rate:** Increase visitor-to-signup ratio by 25% through the new landing page.
*   **Performance:** Achieve a Lighthouse accessibility score of 90+.

## 3. Design System &amp; Visual Identity
### 3.1 Visual Direction
*   **Style:** Premium SaaS + Academic Professionalism.
*   **Key Attributes:** Clean, breathable, modern, "glassmorphism" accents, soft shadows.
*   **Corner Radius:** High-radius (16px+) for a modern, friendly feel.

### 3.2 Design Tokens
*   **Typography:**
    *   Headlines: *Plus Jakarta Sans* (Modern, professional).
    *   Body: *Inter* (High legibility for academic reading).
*   **Color Palette:**
    *   **Primary:** `#2D3282` (Deep Indigo) - Represents trust and intelligence.
    *   **Secondary/Accent:** `#00F5FF` (Electric Cyan) - Represents innovation and AI.
    *   **Neutrals:** Soft grays for backgrounds; high-contrast dark grays for text.
*   **Motion:** Purposeful micro-interactions, section reveals, and smooth state transitions (e.g., card lifts on hover).

## 4. Information Architecture &amp; Page Requirements
### 4.1 Marketing &amp; Public Pages
1.  **Landing Page:** Hero (Vision to Graduation), How it Works (3-step cards), Agent Overview, Testimonials, and FAQ.
2.  **Services Page:** Detailed cards for each AI Agent capability with clear outcome descriptions.
3.  **Resources Page:** A searchable hub for templates (LaTeX, Proposal docs), guides, and checklists.
4.  **Contact Page:** Professional form with university-specific fields and integrated FAQs.

### 4.2 Authentication &amp; Onboarding
1.  **Auth (Sign Up/In):** Split-screen layout with social auth (Google/LinkedIn) and password validation.
2.  **3-Phase Onboarding Wizard:**
    *   **Phase 1 (Profile):** Department, domain, and academic level.
    *   **Phase 2 (Project):** Idea status, tech stack preferences, and timeline.
    *   **Phase 3 (Goals):** Specific help areas (Coding vs. Writing) and AI guidance intensity.

### 4.3 Core Product (The Dashboard)
1.  **Main Overview:** Personalized greeting, "FYP Progress" donut chart, and a grid of "Active Agents."
2.  **Agent Workspace (e.g., Proposal Agent):** A split-view interface featuring:
    *   Left Panel: AI Chat interface for collaboration.
    *   Right Panel: Real-time document editor/preview.
    *   Toolbar: Export to PDF/LaTeX, citation checker, and outline generator.
3.  **Task/Milestone Tracker:** A timeline of upcoming academic deadlines and agent-suggested tasks.

## 5. Functional Requirements
*   **Responsive Design:** Optimized experience across Mobile, Tablet, and Desktop.
*   **AI Agent Workspaces:** Context-specific UIs for different agents (e.g., the "Dev Agent" might show code snippets, while the "Report Agent" shows a document editor).
*   **Progress Persistence:** Onboarding and dashboard tasks must save automatically via "Save &amp; Continue" logic.
*   **Notification System:** Real-time reminders for milestones and agent updates.

## 6. Non-Functional Requirements
*   **Accessibility:** WCAG 2.1 Level AA compliance.
*   **Performance:** Fast initial load times (optimizing 3D assets or heavy gradients).
*   **Scalability:** The design system must allow for the addition of new specialized agents without breaking the UI.

## 7. Deliverables &amp; Roadmap
1.  **Phase 1:** High-fidelity UI mockups for all 10 screens.
2.  **Phase 2:** Design System documentation (Tokens, Component Library).
3.  **Phase 3:** Interactive Prototyping (Onboarding flow &amp; Agent interactions).
4.  **Phase 4:** Frontend implementation-ready assets (React/Tailwind components).