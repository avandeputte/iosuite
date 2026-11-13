---
description: Connect Claude or another AI assistant to the ioThing apps over MCP.
---

# AI assistants (MCP)

ioPix, ioNote, ioCalendar, ioTask, ioRecipe and ioContact are also [Model Context Protocol](https://modelcontextprotocol.io) servers,
at `/mcp` on their own port, so an assistant such as Claude can work with them as you: explore and search the photo
library, search and write notes, read the agenda and add events, add tasks and tick them off, look recipes up and import them from the web, find contacts and file suggestions for them, and,
for admins, check the server's health. ioHealth and the ioSuite start page have no MCP server.

## Turn it on

MCP is **off on a fresh install**. An admin turns it on per app under **Settings › Server** (or `MCP=1` in
`config.env`); while off, `/mcp` doesn't answer at all.

## Connect an assistant

Every assistant signs in with an **app password** (Settings › Account › App passwords, scope "everything") and acts as
that account, with its rights:

```sh
claude mcp add --transport http iocalendar https://calendar.example.com/mcp \
  --header "Authorization: Bearer APP-PASSWORD"
claude mcp add --transport http iopix https://photos.example.com/mcp \
  --header "Authorization: Bearer APP-PASSWORD"
```

Add one per app you want the assistant to use. On a home network without HTTPS, use `http://<host>:<port>/mcp`.

For **Claude Desktop** on a computer in your network, use the `mcp-remote` bridge in `claude_desktop_config.json`
(it needs Node.js):

```json
{
  "mcpServers": {
    "iocalendar": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://calendar.example.com/mcp",
               "--header", "Authorization: Bearer APP-PASSWORD"]
    }
  }
}
```

On the server itself, `.venv/bin/python -m app.mcp --user NAME` serves the same tools over stdio.

## Be careful with admin app passwords

The tools for operating an app (diagnostics, the server log, installing an update) need an admin. An admin's app
password can install code on the server: treat it like a root password, and revoke it when in doubt. For an assistant
that only needs to read and write your own data, use an app password of a non-admin account.

Behind a reverse proxy, `/mcp` must not be buffered; behind Cloudflare Access, it needs a bypass rule. See
[Reverse proxy and HTTPS](reverse-proxy.md) and [Cloudflare](cloudflare.md).
