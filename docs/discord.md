# Forever XP Discord bot

The server's layout lives in [`discord/server.json`](../discord/server.json). The **Discord**
workflow applies it from `main`, so a channel, topic, forum tag or role change is a pull request
like any other. The **Refresh Blizzard notes** workflow posts each new Blizzard change and each new
Blizzard news article to `#forever-announcements` as an embed (changes grouped by class, then race,
then section), and publishes them so servers that follow the channel get them too. To (re)post a
day by hand, run **Actions > Discord** with a date; it replaces the bot's earlier post for that day.

The bot never deletes anything except roles listed in `retired_roles`, never pings anyone, and
never needs Administrator.

## One-time setup (server owner, about three minutes)

1. **Create the bot.** Go to <https://discord.com/developers/applications>, then
   **New Application**, name it **Forever XP**, and accept the developer terms.
   - **General Information:** upload `site/public/brand/logo-512.png` as the app icon.
   - **Bot:** set the same icon, and turn **off** "Public Bot" so only you can add it to servers.
     Leave every "Privileged Gateway Intent" off; the bot doesn't need them.
   - **Bot > Reset Token:** copy the token. Don't paste it anywhere except step 3.
2. **Invite it to Forever-XP.** Go to **OAuth2 > URL Generator**, tick the scope `bot`, then
   the permissions *View Channels, Send Messages, Embed Links, Read Message History,
   Manage Channels, Manage Roles*. Open the generated URL and pick the Forever-XP server.
   (Permission integer: `268520464`.)
3. **Give GitHub the token.** In the repo, go to **Settings > Secrets and variables > Actions**:
   - New repository secret `DISCORD_BOT_TOKEN`: paste the token.
   - Variables tab, new variable `DISCORD_GUILD_ID`: `1564041333495308363` (the Forever-XP server ID).
4. **Apply the layout.** Go to **Actions > Discord > Run workflow**, untick "Only show what would
   change", and run it. The first run with the box ticked shows the plan without touching
   anything.

After that, the #forever-announcements feed starts on its own with the next new Blizzard post.

## Roles

`roles` in `discord/server.json` is listed top to bottom in display order: Admin, Moderator,
Contributor and ForeverScout tester. Admin is a name tag for the server owner, who already has every
permission. A member's name takes the color of their highest role.

- The bot creates missing roles with **no permissions** and not mentionable, keeps each role's
  color and "show separately" (`hoist`) setting as listed, and puts them in the listed order.
- It never changes an existing role's permissions and can only edit roles below its own.
- To remove a role, move its name to `retired_roles`; the bot deletes roles with those names and
  nothing else. Keep the bot's role at the top of Server Settings > Roles; if it isn't, the run
  says which roles it had to leave alone.
- Staff permissions (Moderator) are given by hand in Server Settings > Roles, since a bot can't
  grant permissions it doesn't have.

## Security

- The token lives only in the `DISCORD_BOT_TOKEN` Actions secret. Only workflows on `main` use it;
  pull requests (including from forks) never see it.
- Least privilege: the six permissions above. Manage Roles is needed to make channels read-only
  for members and to create and order the member roles; the bot can't touch roles above its own.
- Messages are posted with mentions disabled, Blizzard's text has Discord formatting escaped,
  link previews are suppressed, and no more than six posts go out per run.
- If the token ever leaks: **Bot > Reset Token** in the developer portal (the old one stops
  working at once), then update the secret.

## Welcome and rules text

`discord/messages/welcome.md` and `discord/messages/rules.md` are posted by the bot in #welcome and
#rules (the `message` key in `discord/server.json`). Edit the file and merge: the bot edits its own
message in place rather than posting a new one. `{#channel-name}` becomes a clickable channel link.
Messages go out with mentions disabled and link previews off, and only in read-only channels.

## Private channels

`private_channels` lists staff-only channels such as #moderator-only. The bot creates one if it's
missing, hidden from @everyone. It never changes an existing one; the run only warns if @everyone
can see it. Who else can see it is set by hand in the channel's Permissions.

## Still done by hand in Discord

- **Rules screening** (new members accept the rules before they can post, react or DM):
  Server Settings > Safety Setup > DM and Spam Protection.
- **Moderator permissions:** Server Settings > Roles > Moderator.
- **Two-factor sign-in** on your Discord account, then **Server Settings > Safety Setup >
  Require 2FA for moderator actions**.

## Next

- Slash commands (`/quest`, `/item`, `/bis`) answered from the site's data, through a Cloudflare
  Worker that verifies Discord's request signatures.
