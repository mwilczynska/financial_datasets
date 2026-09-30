# Repository working notes

## Windows and PowerShell

- This workspace uses Windows PowerShell. Prefer `rg` for searches and use
  `-LiteralPath` with PowerShell file operations. Keep commands separate with
  actual newlines, and avoid passing filesystem operations through another shell.
- Write Python programs to a `.py` file and invoke `python path\to\script.py`.
  Avoid `python -c` for code containing embedded quotes: this environment's
  Windows native argument handling can remove the quotes and turn string
  literals into Python identifiers (`NameError`). Use `apply_patch` to create
  scripts; disposable research scripts belong in ignored `data/interim/`.
- The command runner has sometimes failed before starting PowerShell with
  `helper_unknown_error: setup refresh had errors`. This is a runner/sandbox
  startup problem, rather than a command syntax error. Do not repeatedly change
  shell names or quoting to address it. If a minimal ordinary invocation also
  fails, request a narrowly scoped `require_escalated` invocation with a clear
  justification and let the configured approval reviewer decide. Do not treat
  this note as permission to bypass an approval rejection.
- The Chrome connector can fail with the same pre-launch sandbox error even
  when Chrome and its extension are open. Reset the connector once and retry
  its documented entry point; if it still cannot start, report that limitation
  and use a manual export supplied by the user. Do not mistake this error for
  a website bot wall or repeatedly change browser commands.
- For a command that returns a `session_id`, collect its result with
  `write_stdin`; use `functions.wait` only for a running `functions.exec` cell.
- Keep output bounded: read the relevant file sections and batch independent
  reads. `rg --files` respects ignores; use `rg --files --no-ignore sources/raw`
  when intentionally inspecting downloaded local source caches.
- Read UTF-8 Markdown explicitly with `Get-Content -Encoding UTF8` when using
  Windows PowerShell; its default decoding can display Unicode punctuation
  incorrectly. In Python regular expressions, use raw string literals for
  backslashes to avoid invalid-escape warnings on newer Python versions.

## Data research

- Store downloaded sources in `sources/raw/`; they are ignored by default.
  Record the source URL, access date, content hash, observed coverage, and
  unresolved methodology or redistribution constraints.
- Keep exploratory results separate from production datasets. A research
  recommendation does not establish that a replacement is more accurate;
  distinguish verified observations, vendor claims, and proposed validation.
