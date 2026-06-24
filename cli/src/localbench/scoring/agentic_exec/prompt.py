"""Protocol C prompt construction.

Builds the system message that instructs the model to solve an AppWorld task by
bounded code-as-action: EXACTLY ONE python code block per turn against ``apis.<app>.<api>``,
print what it needs to observe, iterate over observations, and signal a final answer in a
harness-parseable way (bind ``answer`` + emit the ``FINAL_ANSWER`` sentinel) so the HARNESS
calls finalize — because ``complete_task`` is harness-owned and the sandbox forbids the model
calling it.

App/API discovery is exposed ON DEMAND via ``apis.api_docs.*`` (we do NOT dump all ~457 APIs):
the prompt tells the model the three doc calls and the small set of app names, and the model
pulls the specific API signatures it needs.

The task instruction + supervisor email are injected into the prompt. They are fetched by the
loop on the TRUSTED side via a bootstrap block (``apis.supervisor.show_active_task`` /
``show_profile``) so no new sandbox opcode is needed; see ``protocol_c_loop``.

Pure / import-safe: stdlib + the project's ChatMessage type only.
"""

from __future__ import annotations

from localbench._types import ChatMessage
from localbench.scoring.agentic_exec.block_parser import FINAL_ANSWER_SENTINEL

# The app namespaces AppWorld exposes. Kept as a short hint so the model knows where to look
# WITHOUT us dumping every API; it discovers concrete signatures via apis.api_docs.*. If an
# app name drifts in a future AppWorld version, the model can still call
# apis.api_docs.show_app_descriptions() to list them — the loop also offers that at runtime.
_DEFAULT_APP_HINT = (
    "amazon, gmail, phone, simple_note, spotify, splitwise, todoist, venmo, supervisor"
)

_SYSTEM_TEMPLATE = """\
You are an autonomous agent that completes a task in the AppWorld environment by writing \
small Python programs that call documented APIs.

# How you act
Each turn you reply with EXACTLY ONE fenced Python code block:
```python
# your code here
```
The harness runs that block in a stateful Python session and replies with everything the \
block printed (its stdout). Variables persist across turns, so you build up state \
incrementally. Rules you must follow every turn:
- Write EXACTLY ONE ```python block per turn. Never write two blocks, prose-only turns, or \
an empty block.
- Call APIs as `apis.<app>.<api>(...)`. PRINT what you need to see — unprinted values are \
invisible to you.
- Take small steps: explore (print a sample / the shape of a result), then act. Do not try \
to do everything in one block.
- Only the allowed safe builtins and the modules `re`, `json`, `math`, `datetime`, \
`itertools`, `collections`, `functools`, `string`, `statistics`, `decimal`, `fractions` are \
available. There is no file, network, OS, or shell access — solve the task purely through \
the `apis`.

# Discovering APIs (on demand — they are NOT all listed here)
The available apps are: {app_hint}.
To learn the exact APIs and their arguments, call the docs APIs and print them:
- `apis.api_docs.show_app_descriptions()` — list the apps and what they do.
- `apis.api_docs.show_api_descriptions(app_name='spotify')` — list one app's APIs.
- `apis.api_docs.show_api_doc(app_name='spotify', api_name='login')` — full signature + \
return shape for one API.
Look up the specific APIs you need rather than guessing argument names.

# Authentication
Most apps need an access token. Your own account credentials are available from the \
supervisor:
- `apis.supervisor.show_profile()` gives your profile (including your email).
- `apis.supervisor.show_account_passwords()` lists your account passwords per app.
Use those to call the app's `login(username=..., password=...)` and reuse the returned \
`access_token`.

# Finishing the task
You do NOT call any "complete" or "submit" API yourself — that is forbidden and owned by the \
harness. To finish:
1. In a code block, bind the final answer to a variable named exactly `answer` (any JSON-\
serialisable value: a number, a string, a list, etc. — match what the task asks for).
2. On its own line in that same message, write the sentinel:
{sentinel}
When the harness sees `{sentinel}`, it reads your `answer` variable and submits it for you, \
then the task ends. Only finalize once you are confident; you have a limited number of turns.

# The task
{instruction}

Begin. Remember: ONE python block this turn.
"""


def build_system_prompt(
    instruction: str,
    supervisor_email: str | None = None,
    app_hint: str = _DEFAULT_APP_HINT,
) -> str:
    """Render the Protocol C system prompt for one task."""
    body = _SYSTEM_TEMPLATE.format(
        app_hint=app_hint,
        sentinel=FINAL_ANSWER_SENTINEL,
        instruction=instruction.strip(),
    )
    if supervisor_email:
        body += (
            f"\n\n(For reference, your supervisor's email is {supervisor_email}. "
            "Your own email comes from apis.supervisor.show_profile().)"
        )
    return body


def build_initial_messages(
    instruction: str,
    supervisor_email: str | None = None,
    app_hint: str = _DEFAULT_APP_HINT,
) -> list[ChatMessage]:
    """The initial chat history: a system message plus a user kickoff turn.

    The ``user`` kickoff is required, not cosmetic: some chat templates (e.g. Qwen3) cannot
    generate from a system-only history — the request errors / yields an empty first turn — and
    only engage native thinking when the last message is a user turn. A system-only kickoff
    silently degraded those models (wasted turn 1, thinking never engaged). gemma tolerated
    system-only, so adding the kickoff is harness-uniform, not a model-specific hack."""
    return [
        ChatMessage(
            role="system",
            content=build_system_prompt(instruction, supervisor_email, app_hint),
        ),
        ChatMessage(role="user", content="Begin."),
    ]


def format_observation(stdout: str, error: str | None) -> str:
    """Render a sandbox BlockObservation as the user-turn observation text for the model."""
    parts: list[str] = []
    out = stdout.rstrip("\n")
    if out:
        parts.append(out)
    if error:
        parts.append(f"ERROR: {error}")
    if not parts:
        parts.append("(the block ran but printed nothing)")
    body = "\n".join(parts)
    return f"OBSERVATION:\n{body}"
