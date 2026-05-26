# Agent Instructions for Codex

This file defines how Codex should behave in this repository.

## Purpose

Use this file as the base instruction set for all work in this repo. Future Markdown files may add task-specific or folder-specific guidance. Codex must read and apply them using the rules below.

## Instruction Loading Rules

Before making changes, Codex should load instructions in this order:

1. Direct user request in the current conversation
2. This file: `agent.md`
3. Repository-wide instruction files at the repo root, if present:
   - `AGENTS.md`
   - `CLAUDE.md`
   - `GEMINI.md`
   - `README.md`
   - `skills/**/*.md`
   - `docs_state/**/*.md`
   - especially `skills/current-system-state.md` as the latest run-state truth when present
   - and `skills/trading-strategy-research.md` before changing strategy selection, exits, gates, or metric interpretation
4. Folder-local instruction files in the part of the repo being edited:
   - nearest matching `.md` files in the current path and its parent directories
5. Task-specific documentation explicitly referenced by the user or by the code being changed

If two instructions conflict, follow the more specific one.

Conflict priority:

1. Direct user instruction
2. More local file over more global file
3. Newer task-specific file over generic project documentation
4. This file as the default fallback

If a conflict is still ambiguous, Codex must say so explicitly instead of guessing.

## How to Use Future Markdown Files

When new `.md` files are added later, do not ignore them by default.

- If a Markdown file looks instructional, operational, architectural, or task-defining, read it before changing related code.
- If working in a subdirectory, check for local guidance files near that code.
- Do not bulk-read every Markdown file in large repos without reason. Prefer files relevant to the task area.
- If a file name suggests instructions but the scope is unclear, inspect it and state the assumption you are making.

Examples of files that should usually be treated as guidance:

- `AGENTS.md`
- `agent.md`
- `CLAUDE.md`
- `GEMINI.md`
- `CONTRIBUTING.md`
- `ARCHITECTURE.md`
- `docs/**/*.md` when relevant to the task
- `skills/**/*.md`
- `docs_state/**/*.md`
- `skills/current-system-state.md` for the most recent research metrics and system health
- `skills/trading-strategy-research.md` for strategy taxonomy, edge diagnostics, and gate interpretation

## Behavioral Rules

### 1. Think Before Coding

- Do not assume missing requirements.
- State assumptions when they matter.
- If multiple interpretations exist, surface them instead of picking one silently.
- If something important is unclear, ask.
- If a simpler approach exists, say so.

### 2. Simplicity First

- Write the minimum code that solves the requested problem.
- Do not add speculative abstractions, options, or configurability.
- Do not build for hypothetical future use unless explicitly requested.
- Prefer straightforward code over clever code.
- If the solution feels larger than the problem, simplify it.

### 3. Surgical Changes

- Touch only files and lines needed for the request.
- Do not refactor unrelated code.
- Match existing project style and patterns unless instructed otherwise.
- Remove only the unused code introduced by your own changes.
- If unrelated issues are noticed, mention them separately instead of fixing them silently.

### 4. Goal-Driven Execution

Turn requests into verifiable outcomes.

For non-trivial work, define a short plan in this form:

1. Step
2. Verification

Examples:

- Reproduce bug -> verify with failing test or failing command
- Implement fix -> verify with passing test
- Update behavior -> verify with focused manual or automated check

Do not stop at code changes when verification is practical.

## Execution Expectations

- Read relevant context before editing.
- Prefer small diffs.
- Explain tradeoffs briefly when they affect the implementation.
- If blocked, name the blocker clearly.
- If verification was not run, say so explicitly.
- Do not claim success without evidence.

## Default Decision Rules

- When uncertain, favor correctness over speed.
- When choosing between broad and narrow changes, choose narrow.
- When choosing between implicit assumptions and explicit clarification, clarify if the assumption is risky.
- When documentation and code disagree, inspect both and call out the mismatch.

## Output Style

- Be concise.
- Be direct.
- Avoid overstating confidence.
- Separate facts, assumptions, and recommendations when needed.

## Summary

Codex should treat this file as the base operating contract for the repository, then layer future Markdown guidance on top of it according to scope and specificity.
