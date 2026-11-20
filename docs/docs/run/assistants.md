---
description: Connect Claude or another AI assistant to the ioThing apps over MCP.
---

# AI assistants (MCP)

ioPix, ioNote, ioCalendar, ioTask, ioRecipe, ioThings, ioMoney, ioDocs and ioContact are also [Model Context Protocol](https://modelcontextprotocol.io) servers,
at `/mcp` on their own port, so an assistant such as Claude can work with them as you: explore and search the photo
library, search and write notes, read the agenda and add events, add tasks and tick them off, look recipes up and import them from the web, ask about the net worth, the spending and the portfolio, find contacts and file suggestions for them, and,
for admins, check the server's health. ioHealth has no MCP server.

The ioStart start page has **one MCP server for the whole suite**: connect an assistant there once and it gets every
app's tools, named after the app (`iocalendar_add_event`, `iotask_add_task`...), so one request can span apps ("put
Friday's dinner ingredients on the shopping list"). Each call is passed on to that app's own MCP server as you, so each
app still decides what you may see and change there; an app whose own MCP server is off, or where you have no role,
offers nothing. `suite_apps` lists the apps it reaches, and suite admins also get `suite_version` and `update_suite`,
which update every app at once.

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

Add one per app you want the assistant to use, or only ioStart's (`https://home.example.com/mcp`, with an ioStart app
password) for all of them. On a home network without HTTPS, use `http://<host>:<port>/mcp`.

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

On the server itself, `.venv/bin/python -m app.mcp --user NAME` serves the same tools over stdio. It reads the account
and its role once, when it starts: after changing someone's role, restart any stdio server running as them. Starting
one needs the app's `config.env` (with the database password), so it is only for whoever runs the server.

## Be careful with admin app passwords

The tools for operating an app (diagnostics, the server log, updating the suite) need an admin. An admin's app
password can install code on the server: treat it like a root password, and revoke it when in doubt. For an assistant
that only needs to read and write your own data, use an app password of a non-admin account.

Behind a reverse proxy, `/mcp` must not be buffered; behind Cloudflare Access, it needs a bypass rule. See
[Reverse proxy and HTTPS](reverse-proxy.md) and [Cloudflare](cloudflare.md).
