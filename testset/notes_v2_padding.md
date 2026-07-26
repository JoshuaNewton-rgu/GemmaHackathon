# Compilers — lexical analysis (tokenisation)

## What a lexer is for
- Turns a flat character stream into a stream of **tokens**.
- Token = (kind, lexeme, source position). Kind is what the parser cares about.
- Lexeme = the exact characters matched. `count`, `42`, `>=` are lexemes.

## Vocabulary I keep mixing up
- **Lexeme** — the raw text matched.
- **Token** — the classified pair the parser receives.
- **Pattern** — the rule (usually a regex) describing the lexeme set.

## More thoughts
Tokenisation is a really important and interesting part of compilers. It is very
important to understand tokenisation deeply because tokenisation comes up in lots
of exam questions. Tokens tokens tokens. I will definitely go through the lexer
properly later tonight for sure. It is important to note that the lexer is
important. A compiler is a program that compiles code and it is a very important
subject to study for the coursework deadline.
