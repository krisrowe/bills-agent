# Marketplace Registration

Claude Code plugins install through marketplaces. A marketplace is a directory
(local or git-hosted) that lists available plugins. You need a marketplace
registered with Claude Code that includes the `bills` plugin entry.

## Check existing marketplaces

```bash
claude plugin marketplace list
```

If a marketplace you have already carries `bills`, skip to
[Install the plugin](#install-the-plugin).

## Option 1: Create a local marketplace

Lowest barrier — no git repo needed.

```bash
mkdir -p ~/claude-marketplace/.claude-plugin
```

Create `~/claude-marketplace/.claude-plugin/marketplace.json`:

```json
{
  "plugins": [
    {
      "name": "bills",
      "source": {
        "source": "git-subdir",
        "url": "https://github.com/krisrowe/bills-agent.git",
        "path": "claude/plugin"
      },
      "description": "Bill tracking with Monarch recurring cross-reference, promo deadline monitoring, and balance explanation"
    }
  ]
}
```

Register it:

```bash
claude plugin marketplace add ~/claude-marketplace
```

## Option 2: Create a git-hosted marketplace

Same structure as above, but hosted in a git repository so it can be shared
across machines or with others.

1. Create a repo with the `.claude-plugin/marketplace.json` file at its root
   (same content as above).
2. Push to a git host.
3. Register:

```bash
claude plugin marketplace add https://github.com/<owner>/<marketplace-repo>.git
```

## Option 3: Add to an existing marketplace

If you already maintain a marketplace, add the `bills` entry to your
`.claude-plugin/marketplace.json` `plugins` array:

```json
{
  "name": "bills",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/krisrowe/bills-agent.git",
    "path": "claude/plugin"
  },
  "description": "Bill tracking with Monarch recurring cross-reference, promo deadline monitoring, and balance explanation"
}
```

Then update the marketplace:

```bash
claude plugin marketplace update <marketplace-name>
```

## Install the plugin

Once the marketplace is registered and includes `bills`:

```bash
claude plugin install bills@<marketplace-name> --scope project
# or
claude plugin install bills@<marketplace-name> --scope user
```

See [README.md](README.md#installation) for full installation instructions.
