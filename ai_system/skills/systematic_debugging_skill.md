---
name: systematic_debugging
description: Performs structured debugging using root cause analysis instead of guesswork
allowed-tools: ["code_execution"]
model: claude-3
---

# Systematic Debugging Skill

## Purpose
Debug issues using a structured, senior-level approach.

## When to Use
Use when fixing bugs, errors, or unexpected system behavior.

## Rules
- Do not guess fixes
- Always identify root cause before applying a solution
- Use evidence from logs, errors, and system behavior
- Avoid trial-and-error debugging

## Steps
1. Identify the error clearly
2. Analyze logs and outputs
3. Form possible causes (hypotheses)
4. Test each hypothesis logically
5. Identify root cause
6. Apply targeted fix
7. Verify fix works completely
8. Document the issue in read.md

## Output
Clear explanation of root cause, fix, and validation

