# Skill Authoring Guide

A skill is a small package that teaches the agent a reusable workflow.

Required file:

- `SKILL.md`

Optional folders:

- `references/` for detailed text references.
- `assets/` for templates or reusable files.
- `scripts/` for explicit helper scripts.

`SKILL.md` must start with YAML frontmatter:

```yaml
---
name: example-skill
description: Explain what the skill does.
argument-hint: Optional input hint
---
```

The body should describe when to use the skill, the workflow steps, expected outputs, and validation checks.
