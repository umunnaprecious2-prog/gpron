---
name: security_compliance
description: Ensures safe handling of credentials, data, and system security
allowed-tools: []
model: claude-3
---

# Security and Compliance Skill

## Purpose
Protect secrets and user data.

## When to Use
Use when handling APIs, credentials, or user data.

## Rules
- Never hardcode secrets
- Always use .env
- Do not expose sensitive data
- Validate inputs

## Steps
1. Identify sensitive data
2. Move secrets to .env
3. Confirm secure loading
4. Apply access control
5. Validate inputs

## Output
Secure and compliant system setup

