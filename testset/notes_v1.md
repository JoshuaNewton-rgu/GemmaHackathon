# Compilers — lexical analysis (tokenisation)

## What a lexer is for
- Turns a flat character stream into a stream of **tokens**.
- Token = (kind, lexeme, source position). Kind is what the parser cares about.
- Lexeme = the exact characters matched. `count`, `42`, `>=` are lexemes.

## Vocabulary I keep mixing up
- **Lexeme** — the raw text matched.
- **Token** — the classified pair the parser receives.
- **Pattern** — the rule (usually a regex) describing the lexeme set.
