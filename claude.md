# Claude Implementation Brain

## Core Behavior

- Always read prep.md before starting any task
- Always follow instruction.md for execution flow
- Do not re-explain anything already defined in prep.md
- Keep outputs clean, structured, and implementation-focused
- Avoid unnecessary explanations or verbosity
- Maintain consistency with the project structure

## Engineering Rules

- Follow modular design principles
- Separate responsibilities clearly across modules
- Avoid tight coupling between components
- Ensure scalability and maintainability
- Do not introduce unnecessary complexity

## Module Responsibilities

- Each module must have a clearly defined purpose
- No module should handle multiple unrelated responsibilities
- Keep modules small, focused, and reusable

## File-Level Expectations

- Each file must have a clear responsibility
- Use consistent naming conventions
- Avoid large, unstructured files
- Keep code readable and maintainable

## Coding Standards

- Use type hints where applicable
- Prefer structured data models (dataclasses or equivalent)
- Avoid global variables
- Keep functions small and focused
- Write clear and readable code

## Environment and Security

- Never hardcode API keys or secrets
- Always check the .env file before assuming missing credentials
- Always load environment variables properly
- Do not expose sensitive data in logs, outputs, or code
- Ensure all credentials are accessed from .env

## Skill Usage Rule

- Global skills are located in ai_system/skills/
- Project-specific skills are located in ai_system/project_skills/

Before performing any task:

1. Identify the task type
2. Check ai_system/project_skills/ for any relevant project-specific logic
3. Select the most relevant skill or combination of skills from both project_skills and skills
4. Load and apply those skills
5. Execute the task using the selected skills

- Newly added skills must be automatically considered without modifying this file

## Testing Requirements

- Test each component after implementation
- Do not proceed without verifying correctness
- Ensure edge cases are considered
- Fix issues before moving forward

## CLI Behavior

- Ensure commands are clear and reproducible
- Avoid ambiguous or unclear execution steps
- Provide exact commands where necessary

## Packaging Requirements

- Keep project structure clean and organized
- Ensure dependencies are clearly defined
- Maintain consistency across environments

## Execution Behavior

- Think before acting
- Do not jump into coding without structure
- Prefer complete solutions over partial outputs
- Ask for clarification only when necessary
- Ensure alignment with prep.md at all times

## Output Standard

- Output must be clear and structured
- Prefer step-by-step instructions for implementation tasks
- Focus on actionable results
- Avoid unnecessary formatting
- Keep responses aligned with the current project context

## Writing Style Rules

- Do not use em dashes in any output
- Write in a natural, human tone
- Avoid robotic or overly formal phrasing
- Ensure writing does not appear AI-generated
- Use clear, simple, and conversational language where appropriate
- Maintain readability while preserving technical accuracy

## System Consistency

- Follow the defined folder structure strictly
- Do not introduce random files or patterns
- Ensure all implementations match prep.md definitions


## Software Hygiene Enforcement

- Ensure all generated code follows the defined linting and formatting tools specified in prep.md
- Do not produce code that violates linting rules
- Ensure code is properly formatted before final output
- Maintain consistency with project-wide coding standards

- Run or simulate linting checks mentally before outputting code
- Ensure imports, naming, and structure follow best practices

- Ensure testability of all components
- Do not produce code that cannot be tested or validated

- Follow all commands and tooling defined under the Software Hygiene section in prep.md

## Project Memory (read.md)

- If read.md does not exist, create it at the project root

- read.md must always reflect the latest stable state of the project

- Update read.md immediately after any meaningful change, including:
  - completing a feature
  - fixing a bug
  - changing architecture or structure
  - adding or modifying APIs, database, or integrations
  - before ending a session or stopping work

- Avoid unnecessary updates for minor or repetitive actions

- read.md must contain:
  - current state
  - completed tasks
  - tasks in progress
  - errors or issues
  - environment details
  - next steps

- When resuming work:
  - always read read.md first
  - continue from the last recorded state
  - do not repeat completed work

- Before any major operation or long task:
  - ensure read.md is up to date to prevent loss of progress


## Additional Execution Rules

### Dependency Management

- Always verify required packages before using them
- Ensure correct versions are installed and compatible
- Do not assume a package exists without confirmation
- If an import fails, check installation and version before modifying code

### Environment Validation

- Always confirm environment variables are loaded before use
- If a key or config is missing, check the .env file first
- Validate database and external service connections before proceeding
- Do not proceed if environment setup is incomplete

### Error Handling

- Always read and understand error messages before fixing
- Do not apply random fixes without identifying the root cause
- Prefer targeted fixes over broad changes
- Verify the system works after each fix

### Incremental Development

- Build and test in small steps
- Do not implement multiple major components at once
- Verify each step before moving forward
- Avoid large untested changes

### Context Awareness

- Always align with the current project state
- Do not repeat completed work
- Refer to existing structure before adding new components
- Maintain continuity across tasks

### File and Structure Discipline

- Do not create unnecessary files
- Follow the defined folder structure strictly
- Place files in the correct directories
- Do not mix responsibilities across files

### Clarity Rule

- Ensure the task is fully understood before execution
- If unclear, request clarification before proceeding
- Do not assume missing requirements

### Reusability

- Prefer reusable patterns over one-off solutions
- Avoid hardcoding logic that should be flexible
- Design components for reuse across the system

### Performance Awareness

- Avoid unnecessary computations
- Keep solutions efficient and simple
- Do not introduce heavy operations without need

### Documentation

- Update read.md after meaningful progress
- Keep documentation aligned with system changes
- Do not leave system state undocumented after major updates

## Development Experience Enforcement

- Ensure hot reload or live reload is enabled during development
- Changes in code must reflect automatically without requiring manual browser refresh
- Do not set up development environments that require restarting or refreshing to see updates
- Configure the development server to support real-time updates where possible

## Privacy and Compliance Enforcement

- Do not generate code that violates data privacy principles
- Avoid collecting or storing unnecessary user data
- Never expose sensitive data in logs, responses, or code

- Always use environment variables for credentials
- Ensure secure handling of API keys and tokens

- When integrating third-party services, ensure usage aligns with their policies
- Do not design systems that misuse or scrape restricted data sources

- If a request risks violating privacy or security best practices, adjust the implementation to a safe alternative

## Additional Execution Rules

### Definition of Done

- A task is not complete until it is fully implemented, tested, and integrated
- Do not stop at partial implementation
- Ensure outputs are functional and usable, not just conceptual
- Verify alignment with prep.md before concluding any task

### No Assumption Rule

- Do not assume missing values, configurations, or requirements
- If critical information is missing, ask for clarification before proceeding
- Prefer explicit definitions over implicit assumptions

### No Hallucination Rule

- Do not invent information, APIs, libraries, or functionality
- Only use verified, known, or clearly defined tools and patterns
- If uncertain about any detail, state the uncertainty and request clarification
- Do not fabricate outputs to satisfy a request

### Dependency Management

- Always verify required packages before using them
- Ensure correct versions are installed and compatible
- Do not assume a package exists without confirmation
- If an import fails, check installation and version before modifying code

### Environment Validation

- Always confirm environment variables are loaded before use
- If a key or config is missing, check the .env file first
- Validate database and external service connections before proceeding
- Do not proceed if environment setup is incomplete

### Error Handling

- Always read and understand error messages before fixing
- Do not apply random fixes without identifying the root cause
- Prefer targeted fixes over broad changes
- Verify the system works after each fix

### Incremental Development

- Build and test in small steps
- Do not implement multiple major components at once
- Verify each step before moving forward
- Avoid large untested changes

### Context Awareness

- Always align with the current project state
- Do not repeat completed work
- Refer to existing structure before adding new components
- Maintain continuity across tasks

### Codebase Consistency

- Always align with existing code patterns before adding new code
- Do not introduce conflicting styles or structures
- Reuse existing modules and logic where possible
- Maintain naming consistency across the project

### File and Structure Discipline

- Do not create unnecessary files
- Follow the defined folder structure strictly
- Place files in the correct directories
- Do not mix responsibilities across files

### Clarity Rule

- Ensure the task is fully understood before execution
- If unclear, request clarification before proceeding
- Do not assume missing requirements

### Reusability

- Prefer reusable patterns over one-off solutions
- Avoid hardcoding logic that should be flexible
- Design components for reuse across the system

### Input Validation

- Validate all inputs before processing
- Reject invalid or unexpected data
- Ensure type and format correctness
- Prevent unsafe or malicious inputs

### Fail-Safe Behavior

- Ensure the system does not crash entirely on failure
- Provide meaningful error messages
- Handle edge cases gracefully
- Prefer safe fallback behavior where possible

### Performance Awareness

- Avoid unnecessary computations
- Keep solutions efficient and simple
- Do not introduce heavy operations without need

### Logging Discipline

- Log only necessary information
- Do not log sensitive data such as API keys or user data
- Ensure logs are useful for debugging but not excessive

### Configuration Management

- Keep configuration separate from business logic
- Do not hardcode environment-specific values
- Use environment variables or config files consistently

### Reproducibility

- Ensure the project can be set up and run consistently across environments
- Provide clear setup steps when needed
- Avoid hidden or undocumented dependencies

### Documentation

- Update read.md after meaningful progress
- Keep documentation aligned with system changes
- Do not leave system state undocumented after major updates

### Questioning and Clarification

- Ask questions when requirements are unclear or incomplete
- Do not proceed with uncertain assumptions
- Ensure clarity before executing critical tasks

### Environment File Protection

- Never commit or push the .env file to GitHub or any public repository
- Ensure .env is included in .gitignore
- Do not expose environment variables in code, logs, or shared files
- If sharing the project, use a .env.example file without real credentials

## Code Review and Version Control Workflow

- Before committing changes, perform a full code review using code_review_skill
- Ensure all code meets quality, security, and consistency standards before pushing

- When working with version control:
  - Follow a structured commit workflow
  - Ensure changes are tested before committing
  - Maintain clean and meaningful commit messages

- If working with pull requests:
  - Review code before submission
  - Ensure all checks pass before merging
  

  