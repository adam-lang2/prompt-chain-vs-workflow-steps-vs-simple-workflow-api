# Working agreement

## Speed

- Aim to finish every task in **under 5 minutes**. If a task looks like it will
  take longer, say so up front and explain why before starting it.
- Prefer the direct route. Don't over-research, don't re-verify things already
  established in the conversation, and don't explore tangents.
- Batch independent tool calls into a single response rather than running them
  one at a time.

## Scope

- Do what was asked. Don't add unrequested work — no extra refactors, no
  "while I was in there" cleanups, no speculative files.
- If something outside the request looks worth doing, mention it in one line
  and let me decide. Don't just do it.

## Long-running jobs

- For anything long-running, report **incremental progress as a percentage**
  (e.g. `scenario 7/11 — 64%`). Never run a long job that prints nothing until
  it finishes.
- Never pipe a backgrounded long-running command through `tail`, `head`, or any
  other tool that buffers until EOF — it hides progress entirely.
- If a job is taking too long or looks stuck, cancel it and try a different
  approach rather than waiting it out. Tell me what you cancelled and why.

## Output

- Show full tabular and structured results, including every column. Only
  condense if I explicitly ask for it.
