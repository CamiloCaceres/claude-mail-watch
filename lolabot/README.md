# lolabot `watch` command

mail-watch's lolabot engine runs:

```bash
tools/email.sh watch <account>
```

and reads one line of JSON back:

```json
{"account": "agent@example.com", "initialized": false,
 "new": [{"id": "12", "uid": 340, "from": "Boss <boss@example.com>", "subject": "Deploy?", "date": "...", "trust": "operator"}]}
```

[lolabot](https://github.com/23blocks-OS/lolabot) 1.2.0 doesn't ship that command. `watch.patch` adds it to
`tools/email_client.py`: one function (`cmd_watch`) plus its subcommand. It uses lolabot's own account
config, IMAP connection and `resolve_trust`, so credentials and trusted senders stay in lolabot.

- It remembers the highest UID it reported in `emails/<account>/watch-state.json`; the first run records
  the inbox and reports nothing.
- It fetches headers with `BODY.PEEK`, so nothing is marked as read.
- `trust` is by address only. Authentication is checked when the agent reads the message with
  `tools/email.sh read`, which shows the Trust and Auth lines.

Apply it from the lolabot folder:

```bash
curl -fsSLO https://raw.githubusercontent.com/CamiloCaceres/claude-mail-watch/main/lolabot/watch.patch
git apply --check watch.patch && git apply watch.patch && rm watch.patch
tools/email.sh watch <account>   # first run: {"initialized": true, "new": []}
```
