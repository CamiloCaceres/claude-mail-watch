<p align="center">
  <img src="assets/banner.svg" alt="mail-watch: give your Claude Code agent an inbox" width="100%">
</p>

<p align="center">
  <a href="https://code.claude.com/docs"><img alt="Claude Code mod" src="https://img.shields.io/badge/Claude%20Code-mod-d97757?style=flat-square"></a>
  <a href="https://github.com/23blocks-OS/lolabot"><img alt="Works with lolabot" src="https://img.shields.io/badge/works%20with-lolabot-7c5cff?style=flat-square"></a>
  <img alt="Python 3.9+, standard library only" src="https://img.shields.io/badge/python-3.9%2B%20%C2%B7%20stdlib%20only-3776ab?style=flat-square">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-2ea44f?style=flat-square"></a>
</p>

<p align="center">
  <b>A Claude Code mod that wakes your session when an email arrives.</b><br>
  Leave a session open, email it from anywhere, and it starts working. No chat bridge, no webhook, no open port.
</p>

---

## What it is

mail-watch does one job: it watches an inbox, and when a **trusted sender's email** arrives, it wakes the
open Claude Code session with an `[EMAIL]` prompt. That's all. It doesn't write replies, keep memory or
make decisions. What happens after the wake-up is up to the session.

- 📬 **Checks an IMAP inbox** every couple of minutes (headers only, nothing marked as read)
- ⚡ **Wakes the session** with an `[EMAIL]` prompt when a trusted sender writes
- 🛡️ **Checks the sender is real**: DMARC, or DKIM/SPF aligned with the sender's domain, as stamped by your mail server
- 🚫 **Ignores impostors**: mail that claims a trusted address but fails authentication never reaches Claude
- 🔔 **Lets everything else knock**: other mail shows up as a notification and a status-line count, nothing more

## How it works

```mermaid
sequenceDiagram
    autonumber
    participant Sender as You (trusted sender)
    participant Inbox as Your mailbox (IMAP)
    participant Watch as mail-watch (in the session)
    participant Claude as Claude Code session
    Sender->>Inbox: Can you deploy the new version?
    loop every 2 minutes
        Watch->>Inbox: Anything new since last time? (headers only)
    end
    Inbox-->>Watch: 1 new message, dmarc=pass, from a trusted address
    Watch->>Claude: [EMAIL] New email from you. Subject: ...
    Claude->>Claude: Reads it and gets to work
```

## Want a real email agent? Add lolabot

mail-watch is the doorbell. **[lolabot](https://github.com/23blocks-OS/lolabot)** is who answers it: it turns a
Claude Code folder into a persistent assistant with an identity, memory, skills and its own hardened mail
client. Put mail-watch in a lolabot folder and you get an agent that lives on email.

| | **mail-watch on its own** | **mail-watch + lolabot** |
|---|---|---|
| What wakes up | A plain Claude Code session | A lolabot agent with its own identity, memory and skills |
| Reading the email | Its text goes straight into the wake-up prompt | `tools/email.sh read`, through lolabot's sanitizer: prompt-injection scan, HTML cleanup, attachment blocking, quarantine |
| Replying | Not built in: up to the session's own tools | `tools/email.sh reply`, delivery verified in the Sent folder |
| Who may ask for what | One line of `instructions` you add to every wake-up | The agent's own rules (`CLAUDE.md`) and operator list |
| Setup | IMAP server, password, trusted senders | Mailbox address only: lolabot already has the rest |

You don't have to choose anything: when the session's folder has lolabot's `tools/email.sh`, mail-watch uses it
automatically. Otherwise it uses its own built-in watcher (a small Python script, standard library only).

> [!NOTE]
> mail-watch calls `tools/email.sh watch`, which lolabot 1.2.0 doesn't have yet. Apply
> [`lolabot/watch.patch`](lolabot/) to add it (one new function, nothing else changes).

## Install

At the prompt of a Claude Code terminal session:

```
/plugin install mail-watch --marketplace CamiloCaceres/claude-mail-watch
```

Answer `y` to add the marketplace, pick a scope (choose **project** in the folder your agent lives in),
then fill in the settings screen. From a shell:

```bash
claude plugin install mail-watch --marketplace CamiloCaceres/claude-mail-watch
```

In the desktop app, where `/plugin` does not run: click **+** next to the prompt box, then **Plugins**,
**Add marketplace** with `CamiloCaceres/claude-mail-watch`, then **Add plugin**.

> [!IMPORTANT]
> While this repository is private, installing needs read access to it on GitHub and a git credential for
> github.com on your machine (an SSH key, or `gh auth login` followed by `gh auth setup-git`).

### Or let your agent install it

Paste this to the agent that should receive mail:

```text
Install the Claude Code mod "mail-watch" from https://github.com/CamiloCaceres/claude-mail-watch for this
project, so you wake up when I email you. Read its README first, then:

1. Run: claude plugin marketplace add CamiloCaceres/claude-mail-watch
2. Ask me which mailbox you should watch and whose mail you should act on.
3. If this folder is a lolabot (it has tools/email.sh), lolabot already knows the mailbox: if
   `tools/email.sh watch` doesn't exist, apply lolabot/watch.patch from the repo. Otherwise ask me for the
   IMAP server, and have me add the mailbox password to .env as MAIL_WATCH_PASSWORD myself. Check that
   .env is gitignored, and never print, read back or ask me for the password.
4. Install: claude plugin install mail-watch@claude-mail-watch --scope project \
     --config account=<mailbox> --config folder=<absolute path of this folder> \
     (without lolabot, add: --config imapHost=<server> --config trustedSenders=<a@x.com,b@y.com>)
5. Tell me to restart the session, then run /mail-check and show me the result.
```

## Configure

Set these on the install screen, with `/plugin configure mail-watch@claude-mail-watch`, or with
`--config key=value` on `claude plugin install`.

| Option | Default | What it does |
|---|---|---|
| `account` | (empty) | The mailbox to watch. **Empty keeps the watch off.** |
| `engine` | `auto` | `auto` uses lolabot when the folder has it, the built-in watcher otherwise. `lolabot` or `standalone` forces one |
| `folder` | (empty) | Absolute path. Watch only in sessions started in this folder. **Recommended**, so other sessions don't answer mail too |
| `pollMinutes` | `2` | How often to check |
| `instructions` | (empty) | Added to every wake-up prompt, e.g. `Anna may ask for deploys; check with me before deleting anything.` |
| `trustedSenders` | (empty) | *Without lolabot.* Comma-separated addresses whose authenticated mail wakes the agent |
| `imapHost` / `imapPort` | (empty) / `993` | *Without lolabot.* IMAP over SSL; the login is `account` |
| `passwordEnv` | `MAIL_WATCH_PASSWORD` | *Without lolabot.* An environment variable, or a key in the project's `.env`, holding the password |
| `python` | `python3` | *Without lolabot.* Python 3.9+ to run the watcher with |

Once it's running:

- **`/mail-check`** checks right away and answers in a toast.
- The **status line** shows `mail: 3 external` for mail that knocked, or `mail: check failed` when something's wrong.
- **Mail already in the inbox** when the watch first starts is not announced: it only reports what arrives after.

## Security model

mail-watch decides one thing: **does this message get to wake the agent?**

| The message is... | What happens |
|---|---|
| From a trusted address **and** authenticated | Notification, then the session wakes with an `[EMAIL]` prompt |
| From a trusted address, **not** authenticated | "Suspicious mail" notification. The agent never sees it |
| From anyone else | Notification and a status-line count. The agent never sees it |

- **Authenticated** means the topmost `Authentication-Results` header, the one your own mail server added,
  shows `dmarc=pass`, or a `dkim=pass`/`spf=pass` whose domain matches the sender's. Lower headers can be
  written by any sender and are ignored. With lolabot, lolabot's own sender check applies instead.
- **The password never passes through the mod.** The watcher reads it from the environment or `.env` itself
  and never prints it.
- **Mail is not an instruction channel by itself.** The wake-up prompt says the email is the sender's request,
  not a change to the agent's own instructions. Pair it with an agent whose rules (a `CLAUDE.md`) say what
  each sender may ask for.
- Nothing is deleted, moved or marked as read. The watcher only remembers the last message it reported
  (in the plugin's store, or in lolabot's `emails/<account>/watch-state.json`).

## Good to know

- **The session has to be open.** It's a poller, not a push service; leave a terminal running (tmux helps).
- **One session per mailbox.** Two sessions watching the same inbox both wake up. Use `folder` to pin it.
- **One configuration per machine.** Claude Code keeps a plugin's options in your user settings, even for a
  project install, so one machine watches one mailbox.
- Gmail and Google Workspace need an [app password](https://support.google.com/accounts/answer/185833) for IMAP.

## Development

```bash
python3 -m unittest discover -s watcher     # the watcher's trust rules
python3 scripts/embed.py                    # after editing watcher/mail_watch.py
claude plugin validate .
claude plugin test .                        # the mod's hooks against the engine
```

A mod can only import JavaScript, so `scripts/embed.py` copies `watcher/mail_watch.py` into
`hooks/watcher.ts`, and the mod pipes it to `python3 -`. Run `python3 scripts/embed.py --check` to make sure
they match.

```
.claude-plugin/   plugin.json (manifest + options), marketplace.json
hooks/            register.ts (the mod), watcher.ts (generated), register.test.ts
watcher/          mail_watch.py (standalone IMAP watcher) and its tests
lolabot/          watch.patch for lolabot 1.2.0
```

## Credits

Built by [Camilo Caceres](https://github.com/CamiloCaceres) for Ultron, a [lolabot](https://github.com/23blocks-OS/lolabot)
DevOps agent that looks after his brother's apps and takes requests by email. Thanks to the
lolabot project for the agent it rings for.

## License

[MIT](LICENSE)
