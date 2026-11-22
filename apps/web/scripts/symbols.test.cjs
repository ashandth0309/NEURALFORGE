

const test = require("node:test");
const assert = require("node:assert/strict");

const { extractSymbols } = require("./symbols.cjs");

test("extracts a TypeScript function", () => {
  const result = extractSymbols(
    "hello.ts",
    "export function greet() { return 'hello'; }"
  );

  assert.deepEqual(result.symbols, [
    { name: "greet", kind: "function", line: 1 },
  ]);
});

test("extracts an interface and type", () => {
  const result = extractSymbols(
    "models.ts",
    `interface User { id: string }
type UserId = string;`
  );

  assert.deepEqual(result.symbols, [
    { name: "User", kind: "interface", line: 1 },
    { name: "UserId", kind: "type", line: 2 },
  ]);
});

test("extracts class and variable", () => {
  const result = extractSymbols(
    "service.ts",
    `class Service {}
const version = 1;`
  );

  assert.equal(result.symbols.length, 2);
  assert.equal(result.symbols[0].kind, "class");
  assert.equal(result.symbols[1].name, "version");
});

test("supports TSX source files", () => {
  const result = extractSymbols(
    "page.tsx",
    "export default function Page() { return <main />; }"
  );

  assert.equal(result.symbols[0].name, "Page");
});

test("rejects unsupported extensions", () => {
  assert.throws(
    () => extractSymbols("test.py", "print('hello')"),
    TypeError
  );
});

test("rejects oversized source", () => {
  assert.throws(
    () => extractSymbols("large.ts", "x".repeat(1048577)),
    RangeError
  );
});
