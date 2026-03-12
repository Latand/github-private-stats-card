# github-private-stats-card

Кастомна картка GitHub-статики (SVG), яка рахує **private + public** дані через GitHub API token.

## Що показує

- ⭐ Stars (сума `stargazers_count` по твоїх non-fork репозиторіях)
- 🧩 Commits за останні 365 днів
- 🔀 PRs за останні 365 днів
- 🐞 Issues за останні 365 днів
- 📦 К-сть репозиторіїв, куди були commit contributions за останні 365 днів

Результат пишеться у:
- `generated/stats.svg`
- `generated/stats.json`

## Підключення до профільного README

Встав у свій `Latand/Latand`:

```md
<p align="center">
  <img src="https://raw.githubusercontent.com/Latand/github-private-stats-card/main/generated/stats.svg" alt="Latand private github stats" />
</p>
```

## Налаштування секрету

У репозиторії `github-private-stats-card` додай Secret:

- `GH_STATS_TOKEN` = GitHub PAT (classic) зі scope:
  - `repo`
  - `read:user`

> Без цього секрету workflow зупиниться (щоб не оновлювати картку неточними public-only даними).

## Автооновлення

Workflow: `.github/workflows/update-stats.yml`

- запускається щодня по cron (`06:15 UTC`)
- пушить оновлення **лише якщо є зміни** у `stats.svg`/`stats.json`
- можна запустити вручну через **Run workflow**

## Локальний запуск

```bash
export GITHUB_TOKEN=ghp_xxx
export GITHUB_USERNAME=Latand
python scripts/generate_stats.py
```
