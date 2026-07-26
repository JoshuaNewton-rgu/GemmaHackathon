# Compilers — lexical analysis (tokenisation)

## What a lexer is for
- Turns a flat character stream into a stream of **tokens**.
- Token = (kind, lexeme, source position). Kind is what the parser cares about.
- Lexeme = the exact characters matched. `count`, `42`, `>=` are lexemes.

## Vocabulary I keep mixing up
- **Lexeme** — the raw text matched.
- **Token** — the classified pair the parser receives.
- **Pattern** — the rule (usually a regex) describing the lexeme set.

## Regular languages → DFA
Each token pattern is a regular expression, so the whole lexer is one NFA
(union of all patterns) converted to a DFA by subset construction. That is why
lexing is linear in input length: one state transition per character, no backtracking.

## Maximal munch (the longest-match rule)
At each position, take the **longest** lexeme that matches any pattern.
Without it `>=` would lex as `>` then `=`, and `!=` as `!` then `=`.

### Worked example — `x>=42`
| pos | longest match | token |
|---|---|---|
| 0 | `x` | IDENT("x") |
| 1 | `>=` not `>` | OP(GE) |
| 3 | `42` not `4` | INT(42) |

Three tokens, not five. Greedy at each step, but never across a token boundary.

## Ties: same length, two patterns
Break by **rule order** — first pattern declared wins.
This is how keywords work: `while` matches both KEYWORD and IDENT, both length 5,
and KEYWORD is declared first. Otherwise every keyword would arrive as an identifier.

### Where maximal munch bites
- C's `x---y`: munched as `x-- - y`, which then fails to parse. The lexer is happy;
  the parser is not. Longest match is a *lexical* decision made with no grammar context.
- Nested generics `List<List<int>>` — `>>` munches as a shift operator. Real compilers
  special-case this in the parser rather than the lexer.
