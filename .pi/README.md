# Pi configuration

Derived from `.opencode/opencode.json` for Pi 1.2.0. Run `pi` from the
repository root and trust the project when Pi prompts. The project extension
loads `.pi/models.json`; Pi normally loads that file only from its agent directory.
The root `AGENTS.md` is discovered automatically.

The default is `llamacpp/gemma4`, the first local model in the OpenCode config,
which has no explicit default model. Use `/model` to select `Qwen3.5` or `Qwen3.8`,
or start with `pi --model llamacpp/Qwen3.8`. Both Qwen models default to `xhigh`
thinking. Model IDs, display names, context/output limits, and sampling parameters
match OpenCode. Input is configured as text only because the source declares no
image capability. Local token costs are recorded as zero.

Compaction retains 15,000 recent tokens and reserves 20,000 tokens. Provider
request and HTTP idle timeouts are 9,000,000 milliseconds. The HTTP idle setting
applies to all Pi-managed HTTP clients, rather than only this provider.

Only local models are included in the startup/cycling scope. OpenRouter is omitted
because the source disables it; no OpenRouter credential is copied. `enabledModels`
scopes startup/cycling, but does not prohibit manually selecting another provider.

OpenCode's permission rules (including denial of external-directory access and
approval for web access), LSP, watcher exclusions, tool-output pruning, four-turn
retention, sharing disablement, and automatic updates have no direct settings
equivalent in this configuration. Pi's project trust is not a replacement for
those permission rules. Compaction maps the token budgets, not OpenCode's pruning
or turn-count behavior.

Configuration references: [Pi settings](https://pi.dev/docs/latest/settings),
[model configuration](https://pi.dev/docs/latest/models), and
[project configuration](https://pi.dev/docs/latest/configuration).
