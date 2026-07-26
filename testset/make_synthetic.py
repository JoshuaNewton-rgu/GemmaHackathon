"""Regenerate the synthetic eval frames.

These arrived as opaque PNGs with no source, which made them impossible to re-theme
when the contract changed topic — and a test set that cannot follow the contract is a
test set that silently starts scoring the wrong thing. This script is the source.

To be clear about what these are worth: a **rendered mock-up of a web page is read by
a vision model as text**, so passing them proves the pipeline runs and proves nothing
about understanding a real screen. `labels.json` marks them `source: "synthetic"` and
the eval harness keeps them out of the headline number on purpose. They exist so the
loop can be exercised without a capture session, and as the hard-case *shape* the real
captures should copy.

    python testset/make_synthetic.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
W, H = 1024, 640


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def _mono(size: int) -> ImageFont.FreeTypeFont:
    for name in ("consola.ttf", "cour.ttf"):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def _watermark(draw: ImageDraw.ImageDraw, dark: bool) -> None:
    draw.text(
        (W - 16, H - 18),
        "SYNTHETIC FRAME — not a real capture, not quotable",
        font=_font(11),
        fill=(120, 120, 120) if dark else (170, 170, 170),
        anchor="rs",
    )


def video_page(path: Path, *, title: str, channel: str, blurb: str, search: str, dark: bool = True) -> None:
    bg = (13, 13, 13) if dark else (255, 255, 255)
    ink = (255, 255, 255) if dark else (20, 20, 20)
    dim = (150, 150, 150)
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 52], fill=(26, 26, 26) if dark else (245, 245, 245))
    d.text((18, 16), "▶ VideoTube", font=_font(17, True), fill=ink)
    d.rounded_rectangle([136, 13, 400, 39], 13, fill=(45, 45, 45) if dark else (232, 232, 232))
    d.text((148, 19), f"Search: {search}", font=_font(12, True), fill=dim)

    d.rounded_rectangle([40, 78, 800, 504], 8, fill=(0, 0, 0) if dark else (10, 10, 10))
    d.polygon([(398, 274), (398, 318), (440, 296)], fill=(190, 190, 190))
    d.text((40, 520), title, font=_font(20, True), fill=ink)
    d.text((40, 548), f"{channel} · {blurb}", font=_font(13), fill=dim)
    _watermark(d, dark)
    img.save(path)


def pdf_page(path: Path, *, filename: str, heading: str, lines: list[str]) -> None:
    img = Image.new("RGB", (W, H), (60, 63, 65))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 40], fill=(43, 45, 47))
    d.text((16, 12), f"📄 {filename} — 1 / 14", font=_font(13, True), fill=(225, 225, 225))

    d.rectangle([150, 62, 874, 610], fill=(255, 255, 255))
    d.text((186, 96), heading, font=_font(21, True), fill=(15, 15, 15))
    d.line([186, 132, 838, 132], fill=(190, 190, 190))
    y = 156
    for line in lines:
        mono = line.startswith("  ")
        d.text((186, y), line, font=(_mono(14) if mono else _font(14)), fill=(35, 35, 35))
        y += 30
    _watermark(d, dark=False)
    img.save(path)


def social_page(path: Path) -> None:
    img = Image.new("RGB", (W, H), (24, 25, 26))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 50], fill=(36, 37, 38))
    d.text((18, 15), "Friendfeed", font=_font(18, True), fill=(66, 133, 244))
    posts = [
        ("Ellie", "canNOT believe what happened at the flat last night 😂😂"),
        ("Marcus", "rating every dog I met this week — a thread 🐕"),
        ("Priya", "who else is awake. it is 1am. this is not a drill"),
    ]
    y = 74
    for name, text in posts:
        d.rounded_rectangle([40, y, 984, y + 148], 10, fill=(36, 37, 38))
        d.ellipse([60, y + 18, 100, y + 58], fill=(90, 92, 96))
        d.text((112, y + 22), name, font=_font(14, True), fill=(230, 230, 230))
        d.text((112, y + 44), "3h · Public", font=_font(11), fill=(150, 150, 150))
        d.text((60, y + 82), text, font=_font(15), fill=(225, 225, 225))
        d.text((60, y + 116), "👍 412    💬 88    ↗ Share", font=_font(12), fill=(150, 150, 150))
        y += 164
    _watermark(d, dark=True)
    img.save(path)


def chat_page(path: Path) -> None:
    img = Image.new("RGB", (W, H), (49, 51, 56))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 230, H], fill=(43, 45, 49))
    d.text((18, 18), "CS3101 Compilers", font=_font(14, True), fill=(220, 220, 220))
    for i, ch in enumerate(["# general", "# coursework-2", "# lexer-help", "# social"]):
        d.text((18, 58 + i * 30), ch, font=_font(13), fill=(140, 220, 160) if i == 2 else (150, 152, 157))
    d.text((250, 18), "# lexer-help", font=_font(16, True), fill=(235, 235, 235))
    d.line([250, 46, 1000, 46], fill=(60, 62, 68))

    msgs = [
        ("callum", "is anyone else stuck on maximal munch for the >= case"),
        ("me", "yeah — mine lexes it as > then = so the parser dies"),
        ("priya", "you need longest-match at each position, not first-match"),
        ("priya", "and declare KEYWORD before IDENT or `while` comes back as an ident"),
        ("callum", "ohhh that is why my keywords vanished. cheers"),
    ]
    y = 68
    for who, text in msgs:
        d.ellipse([252, y + 2, 284, y + 34], fill=(114, 137, 218) if who == "me" else (90, 140, 110))
        d.text((296, y), who, font=_font(13, True), fill=(240, 240, 240))
        d.text((296, y + 22), text, font=_font(14), fill=(220, 221, 222))
        y += 66
    _watermark(d, dark=True)
    img.save(path)


def editor_page(path: Path) -> None:
    """The on-task screen: their own notes file open in an editor."""
    img = Image.new("RGB", (W, H), (30, 30, 30))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 34], fill=(60, 60, 60))
    d.text((14, 9), "notes_tokenising.md — heid-doon", font=_font(12), fill=(220, 220, 220))
    d.rectangle([0, 34, 210, H], fill=(37, 37, 38))
    for i, name in enumerate(["notes_tokenising.md", "lexer.py", "tokens.py", "tests/"]):
        d.text((16, 52 + i * 26), name, font=_font(12), fill=(255, 255, 255) if i == 0 else (160, 160, 160))

    lines = [
        "# Compilers — lexical analysis (tokenisation)",
        "",
        "## Maximal munch (longest-match rule)",
        "At each position take the LONGEST lexeme matching any pattern.",
        "Without it `>=` lexes as `>` then `=`.",
        "",
        "### Worked example — x>=42",
        "  pos 0  ->  IDENT(\"x\")",
        "  pos 1  ->  OP(GE)      # `>=`, not `>`",
        "  pos 3  ->  INT(42)     # `42`, not `4`",
        "",
        "## Ties broken by rule order",
        "`while` matches KEYWORD and IDENT, both length 5.",
        "KEYWORD is declared first, so keywords survive.",
    ]
    y = 56
    for i, line in enumerate(lines):
        d.text((228, y), str(i + 1).rjust(3), font=_mono(13), fill=(90, 90, 90))
        colour = (200, 200, 200)
        if line.startswith("#"):
            colour = (86, 156, 214)
        elif line.startswith("  "):
            colour = (206, 145, 120)
        d.text((280, y), line, font=_mono(14), fill=colour)
        y += 26
    _watermark(d, dark=True)
    img.save(path)


def main() -> None:
    video_page(
        HERE / "yt_lecture.png",
        search="lexical analysis tokenisation",
        title="Compilers: Lexical Analysis — Tokens, Lexemes and Maximal Munch (Lecture 4)",
        channel="Stanford-style CS Compilers",
        blurb="1.4M views · regex to NFA to DFA, longest-match rule, worked examples",
    )
    video_page(
        HERE / "yt_cats.png",
        search="funny cat compilation",
        title="TRY NOT TO LAUGH 😂 Ultimate Funny Cat Fails Compilation #47",
        channel="PetVids Daily",
        blurb="18M views · cats, fails, 22 minutes of chaos",
    )
    pdf_page(
        HERE / "pdf_notes.png",
        filename="cs3101_lec04_lexical_analysis.pdf",
        heading="4. Lexical Analysis and Tokenisation",
        lines=[
            "A lexer maps a character stream to a token stream.",
            "Each token is a triple: (kind, lexeme, position).",
            "",
            "4.1 Patterns as regular expressions",
            "  IDENT   ::= [A-Za-z_][A-Za-z0-9_]*",
            "  INT     ::= [0-9]+",
            "  OP_GE   ::= >=",
            "",
            "4.2 The longest-match rule (maximal munch)",
            "At each position, prefer the longest matching lexeme.",
            "Ties are resolved by the order the rules are declared.",
        ],
    )
    pdf_page(
        HERE / "wrong_pdf.png",
        filename="bio2043_lec09_krebs_cycle.pdf",
        heading="9. Cellular Respiration: the Krebs Cycle",
        lines=[
            "The citric acid cycle oxidises acetyl-CoA to CO2.",
            "Each turn yields 3 NADH, 1 FADH2 and 1 GTP.",
            "",
            "9.1 Regulation",
            "Citrate synthase is inhibited by ATP and NADH.",
            "Isocitrate dehydrogenase is the main control point.",
            "",
            "9.2 Anaplerotic reactions",
            "Pyruvate carboxylase replenishes oxaloacetate.",
        ],
    )
    social_page(HERE / "social_feed.png")
    chat_page(HERE / "chat_class.png")
    editor_page(HERE / "editor_notes.png")
    print("wrote 7 synthetic frames to", HERE)


if __name__ == "__main__":
    main()
