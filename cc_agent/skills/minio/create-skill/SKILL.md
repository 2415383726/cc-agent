---
name: create-skill
description: Create or refine a reusable CC Agent skill package.
argument-hint: What should this skill help you do?
disable-model-invocation: true
---
# Create Skill

Use this skill when the user wants to turn a repeated workflow into a reusable skill.

1. Identify the workflow, inputs, outputs, decision points, and quality checks.
2. Draft a `SKILL.md` with YAML frontmatter and clear Markdown instructions.
3. Put reusable reference material under `references/`, assets under `assets/`, and executable helpers under `scripts/`.
4. If the user wants it installed, write or package the skill in the workspace and use `SkillInstall`.

Skill names must use only letters, numbers, underscores, and hyphens.
