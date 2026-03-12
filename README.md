# github-private-stats-card

Кастомні GitHub SVG-картки з **private + public** даними (через PAT).

## Що генерується

- `generated/stats.svg` — основна статистика
- `generated/top-langs.svg` — топ мов програмування (по bytes у твоїх non-fork репо)
- `generated/streak.svg` — streak/активні дні/внесок
- `generated/stats.json` — сирі агреговані метрики

## Метрики

### `stats.svg`
- ⭐ Stars (owned non-fork repos)
- 🧩 Commits (last 365d)
- 🔀 PRs (all time)
- 🐞 Issues (all time)
- 📦 Contributed repos (last 365d)

### `top-langs.svg`
- агреговані байти коду по мовах з owned non-fork репозиторіїв

### `streak.svg`
- current streak
- longest streak
- active days (all time)
- contributions (all time)

## Вставка в `Latand/Latand` README

```md
<p align="center">
  <img height="200em" src="https://raw.githubusercontent.com/Latand/github-private-stats-card/main/generated/stats.svg" alt="Latand private stats" />
  <img height="200em" src="https://raw.githubusercontent.com/Latand/github-private-stats-card/main/generated/top-langs.svg" alt="Latand private top langs" />
</p>

<p align="center">
  <img height="180em" src="https://raw.githubusercontent.com/Latand/github-private-stats-card/main/generated/streak.svg" alt="Latand private streak" />
</p>
```

## Secret

У repo settings → Secrets and variables → Actions додай:

- `GH_STATS_TOKEN` = PAT (classic) з scope:
  - `repo`
  - `read:user`

Без цього workflow зупиняється (щоб не публікувати public-only неточну стату).

## Автооновлення

Workflow: `.github/workflows/update-stats.yml`

- щодня по cron: `06:15 UTC`
- `workflow_dispatch` вручну
- пушить зміни тільки якщо змінився контент у `generated/`

## Локальний запуск

```bash
export GITHUB_TOKEN=ghp_xxx
export GITHUB_USERNAME=Latand
python scripts/generate_stats.py
```
