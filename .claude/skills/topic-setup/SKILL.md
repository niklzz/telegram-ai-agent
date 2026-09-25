---
name: topic-setup
description: |
  Create or configure Telegram forum topics for the public Claude/Codex
  Telegram bot. Use when a topic needs a working directory, engine, execution
  mode, stream mode, MCP config, a custom prompt, or new-session posts.
---

# Topic Setup

Use this skill when the user wants a new Telegram forum topic or an existing
topic needs to be connected to a project. Keep all edits public-safe and local
to the user's checkout.

## Inputs To Find

Determine:

- The topic's `thread_id`. The bot does not pass chat or thread ids to the agent.
  Every forum topic is registered in `topic_config.json` automatically when it
  is created, so look the topic up there by its `name`; ask the user for the
  topic name if it is ambiguous.
- `TELEGRAM_BOT_TOKEN` from `.env` or the environment.
- Forum chat ID:
  - Prefer `NOTIFICATION_CHAT_ID` from `.env` when it points to a
    `type=supergroup` chat with `is_forum=true`.
  - If `NOTIFICATION_CHAT_ID` is not set, ask the user for the forum group chat
    id; never guess it from a private chat.
  - Do not use `ALLOWED_USER_IDS[0]` as `chat_id` for project topics unless the
    user explicitly asks for private bot-chat Threaded Mode.
  - If no forum group can be discovered locally, ask the user for the forum
    group chat id instead of creating a private-chat topic.
- Project path for the topic, if this is a project topic.
- Desired `engine`: `claude` or `codex`. Prefer Claude Code when both are
  installed. If the configured engine is missing and the other engine exists,
  runtime switches the topic to the available engine.
- Desired `exec_mode`: `subprocess` for short tasks or `tmux` for persistent
  coding sessions.
- Desired `stream_mode`: usually `live`; alternatives are `verbose` and
  `minimal`.
- Optional per-engine `models` map.

## Create A Topic

If the topic does not exist and the bot is an admin with forum topic rights,
call Telegram Bot API:

Read the bot token from the `TELEGRAM_BOT_TOKEN` environment variable or from
the local `.env` file, then call `createForumTopic` with the forum chat ID and
topic name. Do not print or commit the token.

Before creating, verify the target chat:

```bash
getChat(chat_id) -> type == "supergroup" and is_forum == true
getChatMember(chat_id, bot_id) -> bot is administrator and can_manage_topics == true
```

If the chat is private, stop and re-resolve the forum chat. Private bot-chat
Threaded Mode is only for an explicit user request or a deliberately documented
fallback; it is not the default location for project topics in this project.

The response includes `message_thread_id`. Use it as the topic key in
`topic_config.json`.

If the bot has already auto-registered the topic, read `topic_config.json` and
update the existing entry instead of creating a duplicate.

Users can also create topics manually in Telegram. When the running bot receives
the forum-topic service message, it auto-registers the topic in
`topic_config.json` with generic defaults. The default runtime engine is
`claude`; Codex-only installations automatically switch new topics to
`engine=codex` on first use.

## Configure A Topic

Find the topic config path:

```bash
CONFIG_PATH="${TOPIC_CONFIG_PATH:-./topic_config.json}"
```

If `.env` sets `TOPIC_CONFIG_PATH`, use that value.

For project topics:

- Verify `cwd` exists with `test -d`.
- Use an absolute path.
- Set `type` to `project`.
- Set `mode` to `free`. Public project topics use the normal generic prompt.
- Set `mcp_config` to `null` by default so the bot generates its send-tool MCP
  runtime. Use an existing absolute project MCP config only on explicit request
  after reviewing it for secrets and private dependencies.
- Set `engine`, `exec_mode`, `stream_mode`, and optional model overrides.

Example:

```json
{
  "name": "My Project",
  "type": "project",
  "mode": "free",
  "cwd": "/absolute/path/to/project",
  "mcp_config": null,
  "stream_mode": "live",
  "exec_mode": "tmux",
  "engine": "codex"
}
```

For the bundled demo assistant topic:

```json
{
  "name": "Tasks",
  "type": "assistant",
  "mode": "task",
  "cwd": null,
  "mcp_config": null,
  "stream_mode": "live",
  "exec_mode": "subprocess",
  "engine": "claude"
}
```

Write JSON with 2-space indentation and preserve existing unrelated topics.
`TopicConfig` reloads by file mtime, so a restart is not needed for most field
changes.

Load and preserve the existing `models` map, then update only the requested
engine keys. For new configuration, omit legacy `model`. When migrating a
known provider-specific legacy value, move it to `models[current_engine]`
before clearing `model`; if its provider is uncertain, ask the user.

```json
{
  "models": {
    "codex": "CODEX_MODEL_NAME"
  }
}
```

Runtime resolution is `models[active_engine]`, then legacy `model`, then the
provider default. Manual `/engine` changes preserve the map. During automatic
missing-CLI fallback, the first fallback request uses the provider default; the
saved per-engine override applies from the next topic-config lookup.

## Prompt And Modes

The bot prepends nothing to user messages by default. Standing instructions go
into `prompt`:

- top-level `"prompt"` in `topic_config.json`: default for every topic and
  private chats;
- per-topic `"prompt"`: overrides it; `""` disables the default for that topic.

It is added to the first message of a new session in `subprocess` topics (Claude
Code and Codex) and takes effect after `/clear`; `tmux` topics do not apply it.

`mode` only selects the tool policy: `free` is the standard project/general
set, `task` is a restricted task-management example. A new mode name requires
code changes to the runtime resolver and explicit tool policy, plus public tests.

## Project Folders And Session Posts

- With `PROJECT_TOPICS_DIR` set, the bot creates topics for its subfolders
  itself; do not create them by hand. Folder names to skip go into top-level
  `"project_topics_ignore"`. Deleting such a folder deletes its topic with its
  history.
- With `ANNOUNCE_NEW_SESSIONS=true`, set `"announce": false` on topics whose
  prompts must not be posted to Telegram (work or confidential repositories).

## Confirm

Tell the user:

- Topic name and thread ID.
- `cwd`.
- `engine`.
- `exec_mode`.
- `stream_mode`.
- Stored model overrides and the resolved active model, when configured.
- Whether a restart is required.

## Do Not

- Do not write a `cwd` that does not exist.
- Do not commit `.env`, `topic_config.json`, `.mcp*.json`, session JSON files,
  `tmux_sessions/`, or `data/`.
- Do not copy private prompts or local machine paths into public examples.
- Do not delete topic entries just because a Telegram topic was removed.
