# Telegram AI Agent: continue your AI coding sessions from Telegram

[Русская версия](README.ru.md)

> A fork of [pavel-molyanov/telegram-ai-agent](https://github.com/pavel-molyanov/telegram-ai-agent).
> What is different: [About This Fork](#about-this-fork).

Start a task with Claude Code or Codex at your computer, walk away, and keep
going from your phone in Telegram: the same session, the same context, the same
project folder. When you are back at the computer, you reopen the session and
the messages you sent from the phone are already in its history.

<!-- Screenshot: docs/images/handoff.png -->

## Pick Up Where You Left Off

1. Every project folder has its own Telegram forum topic. The bot creates them
   from a projects folder (`PROJECT_TOPICS_DIR`) and removes them when a
   folder goes away.
2. You start a session at the computer, in a terminal or in VS Code. The bot
   silently posts its first prompt to the project topic, so that topic is at the
   top of the list when you pick up the phone.
3. On the phone, open the topic and tap **Continue ▶️** (or send `/continue`).
   The bot switches the topic to the newest session of that folder and shows
   the last exchanges. Your next message, typed or spoken, continues it with
   the full context.
4. Back at the computer, close the tab you left open and reopen the session
   from the history list (`claude -c` or `claude --resume` in a terminal).

No conversation is copied anywhere. Claude Code and Codex keep every session as
a file under `~/.claude/projects` and `~/.codex/sessions`, grouped by project
folder, and the bot continues that same file. The one condition is that the bot
sees the same files and the same project path as your computer. Details and
limitations: [Project Folders And Session Handoff](#project-folders-and-session-handoff).

## Choose Your Setup

| | Where the agent runs | Computer can be off | Effort |
|---|---|---|---|
| A. Bot on your computer | your computer | no | lowest |
| B. Always-on dev server | the server, you connect over SSH | yes | medium |
| C. Shared files | computer locally, server from the phone | yes | highest |

**A. Bot on the computer you work on.** Install the bot next to your agent CLIs.
Nothing needs syncing: it sees your projects and your session history as they
are. The computer has to stay on and awake while you are away. The setup guide
below covers Linux with systemd; on macOS keeping the bot running is up to you
(not tested in this fork).

**B. An always-on dev server or container (recommended).** Keep projects, agent
CLIs and their history on a machine that never sleeps: a home server, a
container on a NAS, or a VPS. Run the bot there too. At the computer you work on
it over SSH, with VS Code Remote-SSH or a terminal, so every session from every
device lands on the server. Your computer can be off. You need a reachable
machine with SSH; everything else is the same as option A on that machine.
The fork author uses this setup: a dev container on a home NAS.

**C. Computer and server share files (advanced).** Keep running agents locally
on the computer, run the bot on a server, and make both sides see the same files
at the same absolute path: projects on a network share mounted at the same path
on both, and `~/.claude/projects` and `~/.codex/sessions` on the computer
pointing to the server copy (for example symlinks into the share, with the same
home directory path). The paths must match exactly, because sessions are
grouped by folder path. Keep in mind: the history lives on a network disk, so
the share must be mounted for agents to start; both sides must use the same
history retention (`cleanupPeriodDays` in Claude Code settings), or one side
deletes the other's history; the Codex thread list is a local database, so
sessions continued from the phone may appear lower in the Codex picker on the
computer.

In options B and C, whatever the agent does from the phone runs on the server,
with the tools installed there, not on your laptop.

Only the first prompt of a session is posted to Telegram, never the
conversation. Telegram group chats are not end-to-end encrypted, so turn posts
off for work repositories with `"announce": false`.

## What Else The Bot Does

Telegram AI Agent is an open-source Telegram bot for controlling Claude Code and
Codex CLI on your server. It turns Telegram into a remote interface for agentic
coding: open a topic for a project, send tasks from your phone, attach files or
voice notes, watch progress, resume old sessions, and drive the live terminal
UI when the agent needs input.

The repository contains the reusable public bot runtime only. It does not
contain private assistant data, private prompts, runtime state, real IDs,
tokens, or machine-specific deployment config.

## About This Fork

The sections above are about the fork. From [What Else The Bot Does](#what-else-the-bot-does)
down it is the upstream operator manual, kept in sync, with the fork additions
worked in.

Branches:

- `main-fork` (default): upstream plus the changes listed here.
- `main`: untouched mirror of upstream, used for rebasing and for sending
  fixes back.

Differences from upstream:

### Local speech-to-text instead of Deepgram

Upstream transcribes voice messages only through Deepgram, so voice notes need a
paid cloud account and leave your machine. This fork adds `STT_URL`: when set,
voice messages are posted to any OpenAI-compatible
`/v1/audio/transcriptions` endpoint, for example
[speaches](https://github.com/speaches-ai/speaches) running faster-whisper on
the same host or LAN. `STT_MODEL` selects the model name sent to that server.
Deepgram remains the fallback when `STT_URL` is empty, so existing installs
keep working unchanged.

Why it is better: voice works fully offline and for free, audio never leaves
your network, and any Whisper-class model can be swapped in. The local timeout
is 120 seconds to accommodate CPU inference. Current limitation: the request
language is hard-coded to `ru`; change it in
`src/telegram_bot/core/services/transcriber.py` if you speak to the bot in
another language.

### `stream_mode` is honoured in subprocess mode

In upstream, the subprocess path calls the streaming handler without the topic
config, so the mode resolver silently falls back to `verbose`. Setting
`/stream live` in a topic had no effect: every tool event still arrived as a
separate message. The fork passes the topic config through, so `live` and
`minimal` behave as documented.

### No duplicated final answer

Claude's `stream-json` output repeats the last assistant text inside the final
`result` event. Upstream sends both, so every subprocess answer arrived twice.
The fork compares the two and skips the second send when the text is
identical, while still recording the first message's IDs so reply-to-resume
keeps working.

Both streaming fixes are upstream bugs and are candidates for pull requests
back to the original project.

### Nothing is prepended to your messages by default

Upstream glued `prompts/default.md` and a `<telegram-context>` block (chat and
thread ids plus a setup hint) onto the first message of every session, and
changing that meant editing tracked files. The fork prepends nothing unless you
set `prompt` in `topic_config.json`: top level for all topics, per topic to
override, `""` to switch it off. It works the same for Claude Code and Codex and
is picked up without a restart. `mode` still selects the tool policy. See
[Prompt Modes](#prompt-modes).

### `/resume` keeps subprocess topics in subprocess mode

In upstream, picking a session with `/resume` silently switched the topic to
`tmux`. The fork points a `subprocess` topic at the picked session and the next
message continues it, marks the current session in the picker and says which
one was picked. Codex sessions from the VS Code extension are listed too.

### Working from the computer and the phone

- `PROJECT_TOPICS_DIR`: every subfolder of a projects folder gets its own forum
  topic with `cwd` set, and a removed folder deletes its topic, with guards for
  an unmounted disk.
- `/continue` and the **Continue ▶️** button: switch the topic to the newest
  session of its folder, from any engine or client, and show the last exchanges.
- `ANNOUNCE_NEW_SESSIONS`: the first prompt of a session started in a terminal
  or IDE is posted silently to its topic, so the topic is at the top when you
  pick up the phone, and a reply continues that session.

Why: with many project topics, finding and continuing the right conversation
from the phone took longer than the task itself. Details, the way back to the
computer, and limitations are in
[Project Folders And Session Handoff](#project-folders-and-session-handoff).

## What You Can Do

- Run Claude Code or Codex from Telegram private chats or group forum topics.
- Keep one Telegram topic per project, workflow, or long-running agent context.
- Bind a topic to a directory on your VPS, for example
  `/home/user/projects/my-app`.
- Choose Claude Code or Codex per topic.
- Use a persistent `tmux` session for real development work, or a short-lived
  subprocess for simple one-off tasks.
- Send text, photos, documents, forwarded message batches, Telegram rich
  messages, and optional voice messages (Deepgram or a local
  OpenAI-compatible speech-to-text server).
- Add your own text to the first message of new sessions with an optional
  `prompt`, globally or per topic; by default nothing is prepended.
- Open a live TUI snapshot with `/tui` and press buttons for Enter, Esc, arrows,
  digits, refresh, and close.
- Resume saved sessions by replying to previous bot messages or with `/resume`,
  in both `tmux` and `subprocess` topics.
- Pick up on your phone where you stopped at the computer: `/continue` (or the
  **Continue ▶️** button) switches the topic to the newest Claude or Codex
  session of its folder, including sessions started in a terminal or an IDE.
- Mirror a projects folder as forum topics: every subfolder gets its own topic,
  a removed folder loses it.
- Get a silent post with the first prompt of every new session started outside
  the bot, so the right topic is at the top of the list when you need it.
- Restart a stuck topic runtime with `/recycle` and inspect MCP runtime process
  health with `/mcpstatus`.
- Let the agent send messages, images, image galleries, and documents back to
  Telegram through the bundled bot MCP server.
- Render final answers that contain Markdown tables as Telegram rich messages,
  with automatic fallback to plain Telegram text.

## How It Works

The bot runs on the same machine as Claude Code and/or Codex CLI. Telegram is
only the control surface. When you send a message, the bot:

1. checks that your Telegram user ID is allowed;
2. downloads attached media when needed;
3. resolves the current chat or forum topic settings;
4. sends the prompt to Claude Code or Codex in the configured working directory;
5. streams progress and the final answer back to Telegram.

## Rich Final Answers

The bot can read incoming Telegram rich messages, including forwarded rich
posts. Text blocks are normalized into Markdown-like text for the agent, tables
and footnotes stay visible in that text, and rich photo blocks are exposed as
image attachments when Telegram provides files for them. Non-text rich media
without accessible files is kept as explicit placeholders.

Intermediate progress messages are always plain Telegram messages. When the
agent's final answer contains a Markdown table, the bot converts that answer to
Telegram rich message blocks and sends it with Telegram's RichText/RichMessage
API. Final answers without tables stay plain. If Telegram rejects the rich
payload or the installed Telegram library cannot send it, the bot falls back to
the normal text response.

Telegram's public schema for this feature starts at
https://core.telegram.org/type/RichText.

Forum topics are isolated by Telegram `chat_id` and `thread_id`. Each topic can
have its own:

- `cwd`: project directory on the VPS;
- `mode`: prompt mode;
- `engine`: `claude` or `codex`;
- `exec_mode`: `tmux` or `subprocess`;
- `stream_mode`: `verbose`, `live`, or `minimal`;
- `mcp_config`: optional MCP config for the agent;
- `model`: optional provider model override.

## Requirements

You need a Linux machine or VPS where the bot and agent CLIs will run.

- Python 3.12+
- `uv`
- Telegram bot token from `@BotFather`
- Your numeric Telegram user ID from `@userinfobot`
- Claude Code CLI and/or Codex CLI installed for the same Linux user that runs
  the bot
- `tmux` for persistent development sessions
- Optional: a local OpenAI-compatible STT server (`STT_URL`) or a Deepgram API
  key for voice transcription

The bot can run with only one agent CLI installed. It prefers Claude Code by
default, but if Claude Code is missing and Codex is available, a topic can run
with Codex.

Check the server user before continuing:

```bash
python3 --version
uv --version
command -v tmux
command -v claude || true
command -v codex || true
```

At least one of `claude` or `codex` must exist. Also make sure the CLI is
authenticated or configured for the same Linux user that will run the bot.

## Setup Option A: Agent-Assisted

If you already have Claude Code or Codex on the VPS, this is the easiest path.

```bash
git clone https://github.com/niklzz/telegram-ai-agent.git
cd telegram-ai-agent
uv sync
```

Then open Claude Code or Codex in this repository and ask:

```text
Set up this Telegram bot using the bot-setup skill.
```

The repository ships setup skills for both runtimes:

- `.claude/skills/bot-setup/SKILL.md`
- `.codex/skills/bot-setup/SKILL.md`

For forum topics, ask:

```text
Create and configure Telegram forum topics using the topic-setup skill.
```

The topic setup skills live in:

- `.claude/skills/topic-setup/SKILL.md`
- `.codex/skills/topic-setup/SKILL.md`

The agent should ask for your UI language, default engine, execution mode, and
whether to install a systemd service.

## Setup Option B: Manual

Clone and install:

```bash
git clone https://github.com/niklzz/telegram-ai-agent.git
cd telegram-ai-agent
uv sync
cp .env.example .env
cp topic_config.example.json topic_config.json
chmod 600 .env topic_config.json
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=replace-with-botfather-token
ALLOWED_USER_IDS=[123456789]
BOT_LANG=en
STT_URL=
STT_MODEL=deepdml/faster-whisper-large-v3-turbo-ct2
DEEPGRAM_API_KEY=
PROJECT_ROOT=.
APP_ROOT=
AGENT_WORKSPACE_ROOT=
DEFAULT_CWD=.
FILE_CACHE_DIR=./data
TOPIC_CONFIG_PATH=./topic_config.json
TMUX_SESSIONS_DIR=./tmux_sessions
CC_MAX_TURNS=100
CC_INACTIVITY_KILL_SEC=1800
CODEX_AUTO_UPDATE_ENABLED=true
CODEX_UPDATE_TIMEOUT_SEC=180
CODEX_UPDATE_COOLDOWN_SEC=86400
```

Notes:

- `TELEGRAM_BOT_TOKEN`: create a bot in `@BotFather`.
- `ALLOWED_USER_IDS`: JSON array of Telegram user IDs allowed to use the bot.
- `BOT_LANG`: `en` or `ru`. Restart the bot after changing it.
- `PROJECT_ROOT`: the standard single-checkout root. Leave `APP_ROOT` and
  `AGENT_WORKSPACE_ROOT` empty for a normal installation.
- `APP_ROOT` / `AGENT_WORKSPACE_ROOT`: optional advanced split layout. The
  first contains installed code and MCP launchers; the second contains editable
  projects, topic config, session mappings, tmux state, and downloaded files.
- `DEFAULT_CWD`: default working directory for unconfigured topics.
- `STT_URL`: base URL of a local OpenAI-compatible transcription server, for
  example `http://127.0.0.1:8000`. When set, it takes precedence over Deepgram.
- `STT_MODEL`: model name passed to that server. The default matches the
  speaches faster-whisper large-v3-turbo build.
- `DEEPGRAM_API_KEY`: cloud fallback when `STT_URL` is empty. Leave both empty
  if you do not need voice messages.
- `NOTIFICATION_CHAT_ID`: the forum group used by `PROJECT_TOPICS_DIR` and
  `ANNOUNCE_NEW_SESSIONS`; both stay off without it.
- `PROJECT_TOPICS_DIR`: optional absolute folder whose subfolders become forum
  topics, see [Project Folders And Session Handoff](#project-folders-and-session-handoff).
- `ANNOUNCE_NEW_SESSIONS`: `true` to post the first prompt of sessions started
  outside the bot to their topic. Default `false`.
- `CODEX_AUTO_UPDATE_ENABLED`: enables automatic and manual Codex updates.
  Timeout bounds every update; cooldown applies only to automatic updates.

Run in the foreground:

```bash
uv run telegram-bot
```

Open Telegram and send `/start`. Before installing systemd, send one normal
message and check that Claude Code or Codex answers. This catches missing CLI
auth, wrong `PATH`, and bad project paths while logs are still in your terminal.

## Telegram Bot And Group Setup

Private chat works for simple use. For real project work, use a Telegram
supergroup with forum topics.

1. In `@BotFather`, create a bot and copy its token to `.env`.
2. In `@BotFather`, use `/setprivacy` and disable privacy if you want the bot
   to receive normal non-command messages in group topics.
3. Create a Telegram group or supergroup.
4. Enable forum topics in the group settings.
5. Add the bot to the group.
6. Make the bot an admin with rights to read messages, send messages, manage
   topics, and send media/documents.
7. Create topics manually, or use the `topic-setup` skill from Claude
   Code/Codex.

Each topic is a separate agent workspace. You can have one topic for a product
repo, another for a landing page, another for task management, another for
writing posts, and so on. The public repo includes a generic `free` prompt and a
replaceable `task` example. Your own installation can add any prompt modes you
need.

When a new forum topic appears, the running bot registers it in
`topic_config.json` with default settings. It can receive messages immediately,
but it will use defaults until you configure it.

The public `topic_config.json` keys topics by Telegram `message_thread_id`, so
the simplest and recommended setup is one forum group per bot config. To find a
topic ID, start the bot, create or rename a topic, send a message there, then
open the generated `topic_config.json` and edit the new entry.

## Topic Configuration

You can edit `topic_config.json` directly, use `/engine`, `/mode`, and `/stream`
inside Telegram forum topics, or ask the `topic-setup` skill to configure
topics.

Terminology is important: config field `mode` means prompt mode. Telegram
command `/mode` changes execution mode, stored as `exec_mode`.

Example:

```json
{
  "topics": {
    "42": {
      "name": "My App",
      "type": "project",
      "mode": "free",
      "cwd": "/home/user/projects/my-app",
      "mcp_config": null,
      "stream_mode": "live",
      "exec_mode": "tmux",
      "engine": "codex"
    }
  }
}
```

Fields:

- `name`: human-readable label.
- `type`: `assistant` or `project`.
- `mode`: prompt mode. Public modes are `free` and `task`.
- `cwd`: absolute project directory, or `null` to use `DEFAULT_CWD`.
- `mcp_config`: absolute MCP config path, or `null` for bot-generated MCP
  config.
- `stream_mode`: `verbose`, `live`, or `minimal`.
- `exec_mode`: `tmux` or `subprocess`.
- `engine`: `claude` or `codex`.
- `model`: legacy single model override, or `null`.
- `prompt`: optional text prepended to the first message of a new session in
  this topic. Overrides the top-level `prompt`; `""` disables it.
- `announce`: `false` stops new-session posts for this topic (default `true`).
- `models`: optional per-engine overrides keyed by `claude` and/or `codex`.
  Resolution is `models[active_engine]`, then `model`, then the provider
  default; manual `/engine` changes preserve the map. During automatic
  missing-CLI fallback, the first fallback request uses the provider default;
  the saved per-engine override applies from the next request.

Top-level keys next to `topics`:

- `prompt`: default text for every topic without its own `prompt`, including
  private chats. Missing or `""` means nothing is prepended.
- `project_topics_ignore`: folder names that `PROJECT_TOPICS_DIR` must not turn
  into topics.

The bot re-reads the file on change, no restart needed. New prompt text applies
to new sessions (after `/clear`); running sessions keep what they started with.

Use absolute paths for `cwd` and `mcp_config`. Keep `mcp_config` as `null` by
default. Use a project MCP config only after checking it for secrets and private
dependencies; extra servers have their own provider/tool-policy constraints.
Do not commit your real `topic_config.json`.

## Prompt Modes

The config field `mode` selects the tool policy of a topic:

- `free`: the default general/project tool set.
- `task`: a small task-management example with a restricted tool whitelist.

The bot no longer prepends mode prompt files or a `<telegram-context>` block to
your messages. If the agent needs standing instructions, put them into the
`prompt` field of `topic_config.json` (see [Topic Configuration](#topic-configuration)).
It is used in `subprocess` topics for both Claude Code and Codex; `tmux` topics
do not apply it yet. A new mode name requires code changes to the runtime
resolver and an explicit tool policy, plus tests. Keep private data, secrets, personal workflows,
and real customer context out of the public repository.

## Execution Modes

`/mode` chooses how the agent process runs.

### tmux

Use `tmux` for real development work.

The bot starts a persistent terminal session and sends your Telegram messages
directly into Claude Code or Codex TUI. The session keeps context, can survive
bot restarts, and can be inspected with `/tui`.

Use this when:

- you are editing a codebase;
- you want the agent to remember the long-running context;
- the agent may ask permission questions or show interactive menus;
- you want `/resume` and reply-to-session behavior.

`tmux` consumes resources while the session is alive. Use `/recycle` if a topic
runtime is stuck but you want to keep resumable context; use `/kill` when you no
longer need the session.

### subprocess

Use `subprocess` for short tasks.

Each message starts a fresh CLI process, receives the answer, and exits. This is
good for simple questions, notes, small transformations, and tasks where you do
not want a persistent TUI session running in the background. The topic still
keeps its session between messages, and `/resume` and `/continue` switch it
to another saved session without starting tmux.

Private chats use default settings and are good for simple use. Per-topic
controls such as `/mode`, `/stream`, `/engine`, and `/resume` work in forum
topics, because they need a topic-specific config entry.

## Stream Modes

`/stream` controls how much progress the bot sends back to Telegram.

- `verbose`: sends every tool/status event as a separate silent message.
- `live`: keeps tool/status events in one editable progress message.
- `minimal`: suppresses tool/status events completely.

Human-readable intermediate updates remain separate messages in every mode.
The normalized final answer is always sent as one separate logical response.
In subprocess mode, if the final answer is identical to the last streamed text
message, that message is reused instead of being sent again. `live` is the best
default for most project work.

## TUI Mode

`/tui` opens a snapshot of the live tmux pane and attaches control buttons.

This exists because Claude Code and Codex CLIs are terminal applications. They
can show permission prompts, menus, confirmations, model pickers, and other
interactive UI. The bot can write into the terminal and read the transcript, but
sometimes you need to see and steer the TUI directly.

Use `/tui` to:

- inspect what the agent is doing;
- press Enter, Esc, arrows, Tab, Backspace, Ctrl+C, or digits;
- handle permission dialogs;
- handle startup modals (e.g. Codex's update prompt or trust dialog) — when
  the agent shows a modal during initial spawn and the bot can't push input
  through, you'll see "engine started but input is blocked, use /tui";
  open `/tui` and dismiss the modal with the keyboard;
- recover from a stuck-looking interactive state.

`/tail` is a legacy alias for `/tui`.

## Reply, Resume, And Sessions

The bot records which agent session produced each answer. If you reply to an
old bot message, the bot can route your new message back to the matching
session. This is useful when one Telegram topic has multiple historical
sessions.

`/resume` shows saved sessions for the topic working directory, newest first,
marks the current one, and lets you switch back to one of them. Sessions
started outside the bot are listed too: Claude Code and Codex in a terminal or
in the VS Code extension. If the target session belongs to a different engine,
the bot switches the topic engine first. In a `subprocess` topic the pick only
changes which session the next message continues. In a `tmux` topic the bot
can also switch execution mode, and a live tmux session that must be replaced
is stopped as part of the switch.

Slash commands are special in tmux topics: non-bot commands such as `/model` or
`/compact` are sent to the live TUI, not to the replied-to historical session.

`/clear` starts fresh logical context for the current topic. In tmux mode the
bot resets or respawns the tmux session depending on the current state. `/new`
still exists as a legacy alias, but `/clear` is the command shown in the menu.

## Project Folders And Session Handoff

These features are for people who work on the same projects from a computer
and from the phone. They need a forum group in `NOTIFICATION_CHAT_ID` and a
bot that runs on the machine where the agent history lives (`~/.claude/projects`,
`~/.codex/sessions`).

**Topics from folders.** With `PROJECT_TOPICS_DIR=/home/user/projects`, every
subfolder gets a topic with `cwd` set to it: at startup (folders created while
the bot was down are caught up) and then every minute. Folders starting with
`.`, `#` or `@` and names in `project_topics_ignore` are skipped. Topics are
matched by `cwd`, not by name, so renaming a topic is safe and a topic deleted in
Telegram is not recreated (its entry stays in `topic_config.json`; remove the
entry to get the topic back).

When a folder disappears, its topic is deleted **together with its message
history**. To survive an unmounted or half-synced disk, nothing is deleted when
the folder is empty, and a pass that would delete more than 3 topics only logs a
warning. Renaming a folder therefore means a new topic and a deleted old one.

**Continue on the phone.** `/continue` or the **Continue ▶️** keyboard button
switches a `subprocess` topic to the newest session of its folder, whichever
engine and client wrote it, switches the topic engine if needed, and shows the
last three exchanges (prompts and final answers; tool calls and thinking are
left out). Your next message continues that session. Older sessions are one
`/resume` away.

**Back at the computer.** The bot continues the same session file, so the
messages from the phone are in its history. Close the session tab you left open
on the computer and reopen the session from the history list (`claude -c` or
`claude --resume` in a terminal). If you keep writing into the tab that was
open all along, the history forks. `/continue` warns about this when the
session changed less than two minutes ago.

**New-session posts.** With `ANNOUNCE_NEW_SESSIONS=true`, the bot checks every
20 seconds for new sessions in topic folders and posts the first prompt (up to
300 characters) silently to that topic. The post moves the topic to the top of
the list; replying to it continues exactly that session. Only the first prompt
leaves the machine, not the conversation. The bot's own sessions are skipped.
The first check of a topic only records its existing sessions, so old history
is never posted. Put `"announce": false` on topics whose prompts must not reach
Telegram, for example work repositories: Telegram group chats are not end-to-end
encrypted.

Limitations:

- `/continue` works in `subprocess` topics; `tmux` topics use `/resume`.
- In `tmux` topics the bot's TUI sessions look external and would be announced.
- Sessions started in a subfolder of a project are not announced.
- A session continued from the phone runs on the bot machine, with its tools,
  not the ones on your computer.

## Commands

- `/start`: check that the bot responds and show the basic keyboard.
- `/clear`: reset the current topic session.
- `/cancel`: cancel current processing.
- `/language`: show or switch UI language, for example `/language ru`.
- `/mode`: forum topics only; choose `tmux` or `subprocess`. Switching from
  `tmux` to `subprocess` stops the active tmux session.
- `/engine`: forum topics only; choose Claude Code or Codex. Changing engine
  resets the active session.
- `/codex_update`: update Codex CLI manually. It bypasses the automatic
  cooldown but is blocked by another bot-managed update in this process or
  bot-managed active Codex sessions. `/codex_update status` shows the last
  redacted result.
- `/stream`: forum topics only; choose `verbose`, `live`, or `minimal`.
- `/resume`: forum topics only; pick a saved Claude Code or Codex session for
  the current topic working directory.
- `/continue`: forum topics in `subprocess` mode; continue the newest session of
  the topic working directory and show its last exchanges. Also on the keyboard
  as **Continue ▶️**.
- `/tui`: show and control the live tmux TUI.
- `/tail`: legacy alias for `/tui`.
- `/kill`: stop the active tmux session and free resources.
- `/recycle`: restart the active tmux runtime and clean topic-owned MCP
  processes without intentionally clearing resumable context.
- `/mcpstatus`: show redacted MCP process diagnostics for the current topic.

Recommended defaults:

- Real development: `/mode` -> `tmux`, `/stream` -> `live`.
- Short one-off tasks: `/mode` -> `subprocess`, `/stream` -> `minimal` or
  `live`.
- Runtime looks stuck but the session should be preserved: `/recycle`.
- Old session no longer needed: `/kill`.

## MCP Bot Server

The bundled MCP server lets the agent send content back to the current Telegram
topic. Bot-launched sessions receive topic-scoped MCP configuration
automatically.

Public prompt modes allow these generic bot tools:

- `send_message`
- `send_image`
- `send_image_gallery`
- `send_document`

The message, image, gallery, and document tools accept optional Telegram
`parse_mode` values `HTML` or `MarkdownV2`. If Telegram rejects formatting, the
server retries without `parse_mode` where that is safe.

Public prompt modes also allow Context7 documentation tools so agents can fetch
current library/API documentation from configured MCP profiles.

Keep real `.mcp.json` files out of git. They may contain tokens or local paths.

If `mcp_config` is `null`, the bot generates a runtime MCP config containing
the Telegram bot server and the current topic routing. If `mcp_config` points to
an existing file, the bot uses it as the base config and injects the Telegram
bot server into the runtime copy. If the path does not exist, use `null` or fix
the path before relying on project-specific MCP tools.

## Autostart With Systemd

On a VPS, run the bot as a systemd service so it starts after reboot and
restarts after crashes.

```bash
APP_DIR="$(pwd)"
UV_BIN="$(command -v uv)"
USER_NAME="$(whoami)"
tmp_unit="$(mktemp)"
sed \
  -e "s#REPLACE_WITH_LINUX_USER#${USER_NAME}#g" \
  -e "s#REPLACE_WITH_ABSOLUTE_REPO_PATH#${APP_DIR}#g" \
  -e "s#REPLACE_WITH_UV_PATH#${UV_BIN}#g" \
  docs/systemd/telegram-bot.service.template >"${tmp_unit}"
sudo install -m 0644 "${tmp_unit}" /etc/systemd/system/telegram-bot.service
rm -f "${tmp_unit}"

sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

Logs:

```bash
journalctl -u telegram-bot -f
```

Systemd may have a smaller `PATH` than your shell. Before relying on the
service, verify that the service user can run `uv`, `tmux`, and at least one of
`claude` or `codex`. If the CLIs live in a user-local directory, add an
`Environment=PATH=...` line to the unit or use absolute paths.

If systemd stops retrying after repeated crashes:

```bash
sudo systemctl reset-failed telegram-bot
sudo systemctl start telegram-bot
```

## Runtime Files

Do not commit runtime files:

- `.env`
- `topic_config.json`
- `session_mapping.json`
- `channel_sessions.json`
- `announced_sessions.json`
- `tmux_sessions/`
- `data/`
- `.mcp*.json`
- `.venv/`, `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`
- `__pycache__/`, `*.pyc`, `*.pyo`

Commit only public-safe examples and docs, such as `.env.example`,
`topic_config.example.json`, and README files.

## Security Model

This bot is for trusted personal or small-team use. `ALLOWED_USER_IDS` is the
main access control. Anyone who can talk to the bot can ask the configured local
agent CLI to operate in the configured working directory, including file edits
and shell/tool actions allowed by that CLI.

Do not expose the bot to untrusted users. Do not point project topics at
directories you are not willing to let the agent read or edit. Prefer running
the bot under a dedicated low-privilege Linux user. If the bot token leaks,
rotate it in `@BotFather`.

Values loaded from `.env` are treated as opaque strings, so token text such as
`${NAME}` is not expanded. Agent subprocesses start with a constrained
environment: bot tokens and unrelated service credentials are not inherited.
The bot also uses a dedicated workspace-local tmux server by default and
migrates only its own persisted sessions from older installations.

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src/ mcp-servers/bot/server.py
uv run pytest
PYTHONDONTWRITEBYTECODE=1 uv run python -c "import telegram_bot; import telegram_bot.__main__; print('ok')"
```

## Feedback

For the fork-specific changes (local STT, streaming fixes), open an issue in
[niklzz/telegram-ai-agent](https://github.com/niklzz/telegram-ai-agent). For
everything else, the upstream project is the right place.

The original project is made by Pasha Molyanov. I write about business, AI assistants, development, and
launching useful services in my Telegram channel:
[@molyanov_blog](https://t.me/+zJ5qmSsoYediYzdi). My website:
[molyanov.ru](https://molyanov.ru).

## License

MIT
