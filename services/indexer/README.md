
# NEURALFORGE Repository Indexer

## Purpose

Read approved local TypeScript repositories and produce
structured metadata without executing imported source code.

## Supported source files

- `.ts` and `.tsx`
- TypeScript declaration files (`.d.ts`) are excluded.
- Common generated directories are excluded.
- Maximum indexed file size: 1 MiB.
- Maximum indexed files: 1,000.

## Output schema

Each indexed source file contains:

- `path`: Repository-relative source path.
- `sha256`: SHA-256 content hash.
- `size_bytes`: File size in bytes.
- `symbols`: Optional AST-extracted declarations.

Each symbol contains:

- `name`: Declaration name.
- `kind`: Function, class, interface, type, enum or variable.
- `line`: One-based source line number.

## Run

From the repository root:

python -m services.indexer.indexer apps/web --allowed-root .

To include symbols:

python -m services.indexer.indexer apps/web --allowed-root . --symbols

## Tests

python -m unittest discover -s services/indexer/tests -v

node --test apps/web/scripts/symbols.test.cjs

## Current limitations

- Intended for trusted local repositories.
- No database persistence or incremental indexing yet.
- No cross-file dependency graph yet.
- Symbol extraction currently focuses on top-level declarations.
- File traversal and reopening are not fully protected against
  concurrent filesystem changes or symlink races.
- The Node parser is not yet isolated in a restricted sandbox.
