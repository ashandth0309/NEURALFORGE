/* eslint-disable @typescript-eslint/no-require-imports */


const ts = require("typescript");

const MAX_SOURCE_BYTES = 1024 * 1024;

function extractSymbols(filePath, sourceText) {
  if (
    typeof filePath !== "string" ||
    !/\.(ts|tsx)$/i.test(filePath) ||
    typeof sourceText !== "string"
  ) {
    throw new TypeError("Expected TypeScript file and source text");
  }

  if (Buffer.byteLength(sourceText, "utf8") > MAX_SOURCE_BYTES) {
    throw new RangeError("Source file exceeds size limit");
  }

  const kind = filePath.endsWith(".tsx")
    ? ts.ScriptKind.TSX
    : ts.ScriptKind.TS;

  const file = ts.createSourceFile(
    filePath,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    kind
  );

  const symbols = [];

  function record(name, kind, node) {
    const position = file.getLineAndCharacterOfPosition(
      node.getStart(file)
    );

    symbols.push({
      name,
      kind,
      line: position.line + 1,
    });
  }

  function visit(statement) {
    if (ts.isFunctionDeclaration(statement)) {
      record(
        statement.name?.text ?? "default",
        "function",
        statement
      );
    } else if (ts.isClassDeclaration(statement)) {
      record(
        statement.name?.text ?? "default",
        "class",
        statement
      );
    } else if (ts.isInterfaceDeclaration(statement)) {
      record(statement.name.text, "interface", statement);
    } else if (ts.isTypeAliasDeclaration(statement)) {
      record(statement.name.text, "type", statement);
    } else if (ts.isEnumDeclaration(statement)) {
      record(statement.name.text, "enum", statement);
    } else if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        if (ts.isIdentifier(declaration.name)) {
          record(declaration.name.text, "variable", declaration);
        }
      }
    }
  }

  for (const statement of file.statements) {
    visit(statement);
  }

  return {
    file: filePath,
    symbols,
  };
}

module.exports = { extractSymbols };


if (require.main === module) {
  let input = "";
  const MAX_INPUT_BYTES = 2 * 1024 * 1024;

  process.stdin.setEncoding("utf8");

  process.stdin.on("data", (chunk) => {
    input += chunk;

    if (Buffer.byteLength(input, "utf8") > MAX_INPUT_BYTES) {
      console.error("Input exceeds size limit");
      process.exitCode = 1;
      process.stdin.destroy();
    }
  });

  process.stdin.on("end", () => {
    if (process.exitCode) return;

    try {
      const request = JSON.parse(input);

      const result = extractSymbols(
        request.file,
        request.source
      );

      process.stdout.write(JSON.stringify(result) + "\n");
    } catch (error) {
      console.error(
        error instanceof Error
          ? error.message
          : "Parser failed"
      );
      process.exitCode = 1;
    }
  });
}
