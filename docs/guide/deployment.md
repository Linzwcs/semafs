# Deployment (GitHub Pages)

This project uses VitePress docs under `docs/` and deploys with GitHub Actions.

## Repository

- GitHub: `https://github.com/linzwcs/semafs`
- Docs URL after deployment: `https://linzwcs.github.io/semafs/`

## One-time Setup

1. Open repository settings:
   - `Settings` -> `Pages`
2. Set source to:
   - `GitHub Actions`

## Deployment Pipeline

- Workflow file: `.github/workflows/deploy-docs.yml`
- Trigger:
  - push to `main` with changes under `docs/**`
  - manual trigger (`workflow_dispatch`)
- Build steps:
  - run in `docs/`
  - `npm ci`
  - `npm run build`
  - upload `docs/.vitepress/dist`
  - deploy to GitHub Pages

## Base Path Requirement

For project pages, VitePress base must match repository name:

```ts
base: '/semafs/'
```

Configured in:

- `docs/.vitepress/config.ts`

## Local Validation

```bash
cd docs
npm ci
npm run build
npm run preview
```

Open local preview URL and verify links are valid.
