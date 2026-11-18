# Working on eqlens

For any coding agent (Claude Code, Grok, Codex). To *use* eqlens, read `.grok/skills/eqlens/SKILL.md` instead.

## The best features go front and center, always

eqlens is shown in three places: `README.md` (and `README.ja.md`), `USAGE.md`, and the page at
https://scrya.com/eqlens (`website/src/pages/eqlens.astro` in the `worldwide-scrya` repository).
Whenever a feature lands or improves, these are part of the same piece of work:

1. **Lead with the best.** The opening lines of the README and the top of the page (the headline text, the
   formula beside it, and the strip of feature cards under it) show the strongest things eqlens does, newest
   first. Today that order is: the card under a symbol with its plot, the bench, reading aloud, the shader,
   and agents (MCP and the skill). A new feature that beats one of these takes its place; it is never added
   at the bottom of the page.
2. **Show it live.** On the page a feature is something the visitor can use at once, not a description of it.
   The formula at the top must exercise the newest feature.
3. **Keep the order in step.** The `best` list in `eqlens.astro`, the order of its chapters, the README
   opening, and `public/llms.txt` / `llms-full.txt` say the same thing in the same order.
4. **Redraw and ship.** After changing how eqlens draws, run `python3 website/build-eq.py` in
   `worldwide-scrya` so every equation on the site is redrawn, then commit, push, and deploy the site (its
   `CLAUDE.md` has the steps). A change that is pushed but not live is not finished.

## Code

- Tests: `cd tests && python -m unittest`. They must pass before a commit. Add a test with every feature.
- One runtime dependency, matplotlib. Anything more is an optional extra in `pyproject.toml`.
- A formula eqlens cannot honestly work out is refused or shown in words only, never guessed at. Matrices and
  tensors read as arithmetic but are not curves: give them `pop="words"` (`--no-plot`).
- The SVG and PNG carry no script. Only the `.html` fragment does.
- Write for a reader who is new to the formula: plain words, short sentences.
