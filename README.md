# ButterBot

ButterBot is a Discord economy and progression bot built with Python,
`discord.py`, and SQLite. The project is being rebuilt feature by feature with a
focus on deterministic business rules, safe concurrent updates, and a clear
separation between Discord, application, domain, and persistence code.

## Current features

- `/balance` — view a wallet balance
- `/bank balance` — compare liquid wallet money with protected bank storage
- `/bank deposit` — move an exact amount or 25/50/75/100% of wallet money into the bank
- `/give` — transfer whole-dollar currency to another user
- `/daily` — claim a consecutive-day reward
- `/mine` — mine resources, earn currency and XP, and progress through levels
- `/set-balance` — owner-only development command, disabled by default

All money is represented as integer dollars. SQLite data is stored locally and
schema migrations are applied automatically when the bot starts.

## Requirements

- Python 3.11 or newer
- A Discord application and bot token
- Git

The bot requests the Guilds and Server Members intents. Enable **Server Members
Intent** for the bot in the Discord Developer Portal. Invite the bot with the
`bot` and `applications.commands` OAuth2 scopes and grant only the permissions
needed by the commands you intend to use.

## Quick start

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/BrianCheung1/butterbotx.git
   cd butterbotx
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

   On Windows PowerShell, activate it with:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

3. Install ButterBot and its development tools:

   ```bash
   python -m pip install --upgrade pip
   python -m pip install -e ".[dev]"
   ```

4. Create your local configuration:

   ```bash
   cp .env.example .env
   ```

   Set `DISCORD_TOKEN` to the bot token and `OWNER_ID` to the Discord user ID
   that should be authorized for owner-only commands. Discord Developer Mode
   lets you copy a user or guild ID from its context menu.

5. Start the bot from the repository root:

   ```bash
   python -m butterbot
   ```

The default database is created at `data/butterbot.sqlite3`. The `data/`,
`.env`, and `.venv/` paths are ignored by Git.

> [!IMPORTANT]
> Normal ButterBot startup never synchronizes application commands. Command
> publication and removal are explicit operational actions.

For fast testing, enable development commands and synchronize only the configured
development guild:

```bash
python -m butterbot sync-commands development
```

After a reviewed change reaches production, publish the core global command tree
deliberately with development commands disabled:

```bash
python -m butterbot sync-commands production --confirm-production
```

Both synchronization operations log the existing, desired, added, retained, and
removed command names before changing Discord. To remove all previously
synchronized development-guild commands, retain `DEV_GUILD_ID` and run:

```bash
python -m butterbot sync-commands clear-development --confirm
```

## Configuration

Configuration is loaded from environment variables and, for local development,
from `.env`.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DISCORD_TOKEN` | Yes | — | Secret token used to connect the bot to Discord. |
| `OWNER_ID` | Yes | — | Positive Discord user ID authorized for owner-only commands. |
| `DATABASE_PATH` | No | `data/butterbot.sqlite3` | SQLite database path, relative to the working directory if not absolute. |
| `LOG_LEVEL` | No | `INFO` | Python logging level. |
| `ENABLE_DEV_COMMANDS` | No | `false` | Strict `true`/`false` switch for development commands. |
| `DEV_GUILD_ID` | Only when development commands are enabled | — | Positive guild ID where development commands are registered. |
| `VAL_KEY` | Not currently | — | Reserved for the future Valorant feature. |

Never commit `.env` or expose the Discord token in logs, screenshots, issues, or
pull requests.

When `ENABLE_DEV_COMMANDS=false`, development extensions are not loaded and
`/set-balance` is absent from the local command tree. Discord stores registered
guild commands remotely, so disabling the setting does not remove commands that
were synchronized previously; use the explicit `clear-development` operation to
remove them. Production synchronization rejects `ENABLE_DEV_COMMANDS=true`, and
development-only commands are never loaded into its command tree.

## Project structure

```text
butterbotx/
├── src/butterbot/
│   ├── application/       Use cases and narrow repository protocols
│   ├── discord_app/       Discord bot lifecycle, extensions, cogs, and formatting
│   ├── domain/            Discord- and database-independent business rules
│   ├── infrastructure/    SQLite repositories, migrations, and concrete adapters
│   ├── config.py          Typed environment configuration
│   ├── logging_config.py  Application logging setup
│   └── main.py            Process startup and shutdown
├── tests/
│   ├── unit/              Domain, application-service, configuration, and cog tests
│   └── integration/       Temporary-SQLite repository and migration tests
├── .env.example           Safe configuration template
└── pyproject.toml         Package metadata and tool configuration
```

The dependency direction is:

```text
Discord presentation
        ↓
application use cases
        ↓
domain rules and repository protocols
        ↓
infrastructure implementations
```

Discord cogs validate interactions and render responses. Application services
coordinate use cases. Domain modules contain plain Python business rules.
Repositories own SQL and atomic transactions. Dependencies are constructed in
`discord_app/bot.py`, and extensions are selected explicitly in
`discord_app/extensions.py`.

## Adding a slash command

Develop commands as complete, focused vertical slices rather than placing
business logic in a cog.

1. **Define the behavior.** Choose a short, consistent public command name and
   document validation, authorization, persistence, concurrency, and error
   behavior before coding.
2. **Add domain rules if needed.** Put deterministic calculations and business
   concepts in a focused module under `src/butterbot/domain/`. Domain code must
   not import Discord, SQL, or HTTP libraries.
3. **Add an application use case.** Create an action-named service such as
   `ClaimDaily` or `Mine` under the relevant `application/` feature package.
   Define a narrow `Protocol` beside the use case when persistence or an
   external service is required.
4. **Implement infrastructure.** Add a responsibility-named adapter such as
   `SQLiteMiningRepository`. Keep SQL out of cogs and preserve business
   invariants in one transaction when multiple writes must succeed together.
5. **Add a migration when state changes.** Create the next numbered file under
   `src/butterbot/infrastructure/database/migrations/`, using the
   `NNN_description.sql` convention. Never edit a migration after it has been
   applied; add a new migration instead.
6. **Compose the dependency.** Construct the repository and use case in
   `discord_app/bot.py`, with explicit ownership and shutdown for long-lived
   resources.
7. **Create the cog.** Add a focused module under `discord_app/cogs/`. The cog
   should handle Discord validation, permissions, interaction response rules,
   and presentation, then call the application use case.
8. **Register the extension.** Add its module to `CORE_EXTENSION_MODULES`, or to
   `DEV_EXTENSION_MODULES` only when it is intentionally development-only.
9. **Add permanent tests.** Unit-test domain rules, application behavior, and
   command rendering. Use a temporary database for repository, migration,
   rollback, and concurrency tests.

Follow existing slices such as `/balance` for a read-only command and `/daily`
or `/mine` for an atomic state-changing command. Prefer names that state a
responsibility—`TransferMoney`, `Wallet`, and `SQLiteWalletRepository`—over
catch-all names such as `Manager`, `Utils`, or `Helpers`.

## Database migrations

Migrations run in numeric order during bot startup and are recorded in the
`schema_migrations` table with a checksum. Startup fails if an already-applied
migration file has changed. To add schema state:

1. Find the latest migration number in
   `src/butterbot/infrastructure/database/migrations/`.
2. Add the next number, for example `004_create_example_state.sql`.
3. Keep feature-owned state in a cohesive table with explicit foreign keys and
   deletion behavior where appropriate.
4. Add or update migration and repository integration tests.

Do not add feature-specific state to `users` merely because it belongs to a
user. A repository operation may still update multiple related tables in one
atomic transaction.

## Tests and quality checks

Run the complete test suite:

```bash
pytest
```

Run all required quality gates before opening a pull request:

```bash
ruff format --check .
ruff check .
pyright
pytest
git diff --check
```

To apply Ruff formatting locally, run `ruff format .`.

## Contributing

- Keep pull requests focused on one feature or fix.
- Explain intentional user-visible behavior changes.
- Add a regression test for every confirmed bug.
- Use timezone-aware UTC values for persisted times and dates.
- Use integer dollars for money; never persist floating-point currency.
- Do not add generic frameworks or placeholder abstractions for future work.
- Do not commit databases, virtual environments, local configuration, or
  secrets.

Before submitting a change, review the diff for unrelated files and include the
quality-gate results in the pull request description.
