# NEURALFORGE — Architecture

## Mission
Build an AI-assisted repository intelligence workspace that
indexes source code and provides evidence-linked answers and
human-reviewed change proposals.

## First vertical slice
A developer selects a permitted local TypeScript repository,
indexes its source files, and inspects extracted file and
symbol information.

## Planned components
- Web: Next.js 16.4.6, React 19.3.0, TypeScript
- Indexing engine: Python, parser to be selected and tested
- API: FastAPI, introduced when required
- Persistence: PostgreSQL, introduced when required
- Background processing: introduced when required

## Trust boundaries
- Repository content is untrusted input.
- Repository paths must remain within explicitly allowed roots.
- Imported code is never executed during indexing.
- AI-generated proposals cannot automatically modify or merge code.
- Secrets and environment files must not be indexed.

## Milestone 01 acceptance
- Repository structure reviewed
- Frontend starts locally
- ESLint passes
- Production build passes
- Architecture documented
