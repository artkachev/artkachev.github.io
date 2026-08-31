# Когда публикация сломалась

## Скрипт отказался заливать

| Сообщение | Причина и что делать |
|---|---|
| `не задан удалённый репозиторий origin` | `git remote add origin https://github.com/<владелец>/<репо>.git` |
| `репозиторий проекта … не совпадает с site.json` | Это защита. Не обходить — проверить, тот ли проект и тот ли `repo` в настройках |
| `требует явного подтверждения` | Добавить `--confirm`, но только после согласия человека |
| `есть чужие изменения, которые не наложились` | Владелец или кто-то ещё правил репозиторий. `git fetch`, `git rebase origin/main`, разрешить конфликт вручную |
| `нечего заливать` | Сайт не собран: сначала `build` |

## Приглашение в соавторы не принято

```bash
gh api /user/repository_invitations --jq '.[] | "\(.id)\t\(.repository.full_name)"'
gh api -X PATCH /user/repository_invitations/<id>
```

## Деплой не запустился

Проверить, что владелец выбрал Source: GitHub Actions.

```bash
gh api /repos/<владелец>/<репо>/pages --jq '{status,build_type,html_url}'
gh run list --repo <владелец>/<репо> --limit 3
gh run watch <id> --repo <владелец>/<репо>
```

`build_type` должен быть `workflow`. Если стоит `legacy`, попросить владельца
переключить — у соавтора нет прав на настройки репозитория.

## Обложки не скачались

`import` возвращает код 3 и список хешей в `cover_failures`. Причина обычно —
недоступность серверов Spotify. Повторить позже или скачать через другую сеть:

```bash
python3 -c "
import sys; sys.path.insert(0,'<skill-base>/scripts'); import covers
print(covers.download('<проект>', ['<хеш>']))"
```

Сайт с недостающей обложкой не публиковать — на плитке будет дыра.

## Сайт залит, но не открывается

Первый деплой Pages занимает до пяти минут. Дальше:

```bash
python3 -c "
import sys; sys.path.insert(0,'<skill-base>/scripts')
import config, publish
site = config.load_site('<проект>/site.json')
print(publish.verify_live(site, sample_cover='<хеш>'))"
```

Все три проверки должны вернуть 200.
