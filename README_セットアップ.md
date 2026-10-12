# unmei-x-bot — 運命の命式 X自動投稿（X API課金なし）

対象アカウント: **@unmei_meishiki_**（@iching_kobo とは**別アカウント・完全独立**）
毎朝 **5:00 JST**（cron `0 20 * * *` UTC）に GitHub Actions がヘッドレス Chromium で x.com へ投稿。

> @iching_kobo との関係: このリポジトリは別系統です。@iching_kobo の投稿（既存の iching-app リポジトリ）には
> 一切影響しません。アカウントもセッションも別なので、片方の不具合が他方へ波及しません。

## セットアップ（クリック中心・3手）

### 1) リポジトリを作る（1クリック・事前入力済み）
https://github.com/new?name=unmei-x-bot&description=%E9%81%8B%E5%91%BD%E3%81%AE%E5%91%BD%E5%BC%8F+X%E8%87%AA%E5%8B%95%E6%8A%95%E7%A8%BF%EF%BC%88%40unmei_meishiki_%EF%BC%89&visibility=private
→ Private のまま **Create repository** を押す。

### 2) ワークフローを1クリックでコミット（あなたの明示操作が必要な唯一のファイル）
事前入力URL（開いて「Commit changes」を押すだけ）:

https://github.com/okada20200101/unmei-x-bot/new/main?filename=.github%2Fworkflows%2Fx_bot.yml&value=name%3A%20X%20daily%20post%20%28unmei%20%2F%20%40unmei_meishiki_%29%0A%0A%23%20%E6%AF%8E%E6%9C%9D%205%3A00%20JST%20%3D%2020%3A00%20UTC%EF%BC%88%E5%89%8D%E6%97%A5%EF%BC%89%E3%80%82JST%20%3D%20UTC%2B9%E3%80%82%0A%23%20%E5%AF%BE%E8%B1%A1%E3%82%A2%E3%82%AB%E3%82%A6%E3%83%B3%E3%83%88%3A%20%40unmei_meishiki_%EF%BC%88%40iching_kobo%20%E3%81%A8%E3%81%AF%E5%88%A5%E3%82%A2%E3%82%AB%E3%82%A6%E3%83%B3%E3%83%88%E3%83%BB%E5%AE%8C%E5%85%A8%E7%8B%AC%E7%AB%8B%EF%BC%89%0Aon%3A%0A%20%20schedule%3A%0A%20%20%20%20-%20cron%3A%20%220%2020%20%2A%20%2A%20%2A%22%0A%20%20workflow_dispatch%3A%0A%20%20%20%20inputs%3A%0A%20%20%20%20%20%20dry_run%3A%0A%20%20%20%20%20%20%20%20description%3A%20%221%20%3D%20%E6%8A%95%E7%A8%BF%E3%81%9B%E3%81%9A%E6%A4%9C%E8%A8%BC%E3%81%A0%E3%81%91%22%0A%20%20%20%20%20%20%20%20default%3A%20%220%22%0A%0Aconcurrency%3A%0A%20%20group%3A%20x-daily%0A%20%20cancel-in-progress%3A%20false%0A%0Ajobs%3A%0A%20%20post%3A%0A%20%20%20%20runs-on%3A%20ubuntu-latest%0A%20%20%20%20timeout-minutes%3A%2030%0A%20%20%20%20steps%3A%0A%20%20%20%20%20%20-%20uses%3A%20actions%2Fcheckout%40v4%0A%20%20%20%20%20%20-%20uses%3A%20actions%2Fsetup-python%40v5%0A%20%20%20%20%20%20%20%20with%3A%0A%20%20%20%20%20%20%20%20%20%20python-version%3A%20%223.12%22%0A%20%20%20%20%20%20-%20name%3A%20Run%20daily%20poster%0A%20%20%20%20%20%20%20%20env%3A%0A%20%20%20%20%20%20%20%20%20%20TZ%3A%20Asia%2FTokyo%0A%20%20%20%20%20%20%20%20%20%20X_STORAGE_STATE%3A%20%24%7B%7B%20secrets.X_STORAGE_STATE%20%7D%7D%20%20%20%23%20%40unmei_meishiki_%20%E3%81%AE%E3%82%BB%E3%83%83%E3%82%B7%E3%83%A7%E3%83%B3%28storage_state%20JSON%29%0A%20%20%20%20%20%20%20%20%20%20POSTS_ENDPOINT%3A%20%20%20%24%7B%7B%20secrets.POSTS_ENDPOINT%20%7D%7D%20%20%20%23%20%E5%BD%93%E6%97%A5%E3%81%AE1%E6%9C%AC%E3%82%92%E8%BF%94%E3%81%99URL%0A%20%20%20%20%20%20%20%20%20%20ADVANCE_ENDPOINT%3A%20%24%7B%7B%20secrets.ADVANCE_ENDPOINT%20%7D%7D%20%23%20%E6%8A%95%E7%A8%BF%E5%BE%8C%E3%81%AB%E3%82%AB%E3%83%BC%E3%82%BD%E3%83%AB%E3%82%92%E9%80%B2%E3%82%81%E3%82%8BURL%0A%20%20%20%20%20%20%20%20%20%20ADVANCE_TOKEN%3A%20%20%20%20%24%7B%7B%20secrets.ADVANCE_TOKEN%20%7D%7D%0A%20%20%20%20%20%20%20%20%20%20DRY_RUN%3A%20%24%7B%7B%20github.event.inputs.dry_run%20%7C%7C%20%270%27%20%7D%7D%0A%20%20%20%20%20%20%20%20run%3A%20bash%20automation%2Fx_daily%2Fci.sh%0A%20%20%20%20%20%20-%20name%3A%20Upload%20log%20%26%20state%0A%20%20%20%20%20%20%20%20if%3A%20always%28%29%0A%20%20%20%20%20%20%20%20uses%3A%20actions%2Fupload-artifact%40v4%0A%20%20%20%20%20%20%20%20with%3A%0A%20%20%20%20%20%20%20%20%20%20name%3A%20x-daily-state%0A%20%20%20%20%20%20%20%20%20%20path%3A%20%7C%0A%20%20%20%20%20%20%20%20%20%20%20%20automation%2Fx_daily%2Fstate.json%0A%20%20%20%20%20%20%20%20%20%20%20%20automation%2Fx_daily%2Flast_run.log%0A%20%20%20%20%20%20%20%20%20%20if-no-files-found%3A%20ignore%0A

※ GitHubユーザー名が `okada20200101` と違う場合はURL中の `okada20200101` を置換:
https://github.com/<あなたのGitHubユーザー名>/unmei-x-bot/new/main?filename=.github%2Fworkflows%2Fx_bot.yml&value=name%3A%20X%20daily%20post%20%28unmei%20%2F%20%40unmei_meishiki_%29%0A%0A%23%20%E6%AF%8E%E6%9C%9D%205%3A00%20JST%20%3D%2020%3A00%20UTC%EF%BC%88%E5%89%8D%E6%97%A5%EF%BC%89%E3%80%82JST%20%3D%20UTC%2B9%E3%80%82%0A%23%20%E5%AF%BE%E8%B1%A1%E3%82%A2%E3%82%AB%E3%82%A6%E3%83%B3%E3%83%88%3A%20%40unmei_meishiki_%EF%BC%88%40iching_kobo%20%E3%81%A8%E3%81%AF%E5%88%A5%E3%82%A2%E3%82%AB%E3%82%A6%E3%83%B3%E3%83%88%E3%83%BB%E5%AE%8C%E5%85%A8%E7%8B%AC%E7%AB%8B%EF%BC%89%0Aon%3A%0A%20%20schedule%3A%0A%20%20%20%20-%20cron%3A%20%220%2020%20%2A%20%2A%20%2A%22%0A%20%20workflow_dispatch%3A%0A%20%20%20%20inputs%3A%0A%20%20%20%20%20%20dry_run%3A%0A%20%20%20%20%20%20%20%20description%3A%20%221%20%3D%20%E6%8A%95%E7%A8%BF%E3%81%9B%E3%81%9A%E6%A4%9C%E8%A8%BC%E3%81%A0%E3%81%91%22%0A%20%20%20%20%20%20%20%20default%3A%20%220%22%0A%0Aconcurrency%3A%0A%20%20group%3A%20x-daily%0A%20%20cancel-in-progress%3A%20false%0A%0Ajobs%3A%0A%20%20post%3A%0A%20%20%20%20runs-on%3A%20ubuntu-latest%0A%20%20%20%20timeout-minutes%3A%2030%0A%20%20%20%20steps%3A%0A%20%20%20%20%20%20-%20uses%3A%20actions%2Fcheckout%40v4%0A%20%20%20%20%20%20-%20uses%3A%20actions%2Fsetup-python%40v5%0A%20%20%20%20%20%20%20%20with%3A%0A%20%20%20%20%20%20%20%20%20%20python-version%3A%20%223.12%22%0A%20%20%20%20%20%20-%20name%3A%20Run%20daily%20poster%0A%20%20%20%20%20%20%20%20env%3A%0A%20%20%20%20%20%20%20%20%20%20TZ%3A%20Asia%2FTokyo%0A%20%20%20%20%20%20%20%20%20%20X_STORAGE_STATE%3A%20%24%7B%7B%20secrets.X_STORAGE_STATE%20%7D%7D%20%20%20%23%20%40unmei_meishiki_%20%E3%81%AE%E3%82%BB%E3%83%83%E3%82%B7%E3%83%A7%E3%83%B3%28storage_state%20JSON%29%0A%20%20%20%20%20%20%20%20%20%20POSTS_ENDPOINT%3A%20%20%20%24%7B%7B%20secrets.POSTS_ENDPOINT%20%7D%7D%20%20%20%23%20%E5%BD%93%E6%97%A5%E3%81%AE1%E6%9C%AC%E3%82%92%E8%BF%94%E3%81%99URL%0A%20%20%20%20%20%20%20%20%20%20ADVANCE_ENDPOINT%3A%20%24%7B%7B%20secrets.ADVANCE_ENDPOINT%20%7D%7D%20%23%20%E6%8A%95%E7%A8%BF%E5%BE%8C%E3%81%AB%E3%82%AB%E3%83%BC%E3%82%BD%E3%83%AB%E3%82%92%E9%80%B2%E3%82%81%E3%82%8BURL%0A%20%20%20%20%20%20%20%20%20%20ADVANCE_TOKEN%3A%20%20%20%20%24%7B%7B%20secrets.ADVANCE_TOKEN%20%7D%7D%0A%20%20%20%20%20%20%20%20%20%20DRY_RUN%3A%20%24%7B%7B%20github.event.inputs.dry_run%20%7C%7C%20%270%27%20%7D%7D%0A%20%20%20%20%20%20%20%20run%3A%20bash%20automation%2Fx_daily%2Fci.sh%0A%20%20%20%20%20%20-%20name%3A%20Upload%20log%20%26%20state%0A%20%20%20%20%20%20%20%20if%3A%20always%28%29%0A%20%20%20%20%20%20%20%20uses%3A%20actions%2Fupload-artifact%40v4%0A%20%20%20%20%20%20%20%20with%3A%0A%20%20%20%20%20%20%20%20%20%20name%3A%20x-daily-state%0A%20%20%20%20%20%20%20%20%20%20path%3A%20%7C%0A%20%20%20%20%20%20%20%20%20%20%20%20automation%2Fx_daily%2Fstate.json%0A%20%20%20%20%20%20%20%20%20%20%20%20automation%2Fx_daily%2Flast_run.log%0A%20%20%20%20%20%20%20%20%20%20if-no-files-found%3A%20ignore%0A

### 3) 残りのファイルをアップロード
zipを展開し、中身（`automation/` `worker_patch.js`）をまとめてD&D:
https://github.com/okada20200101/unmei-x-bot/upload/main

## Secrets（Settings → Secrets and variables → Actions → New repository secret）
| 名前 | 値 |
|---|---|
| `X_STORAGE_STATE` | **@unmei_meishiki_** のセッション（Cookie-EditorのExport JSONを `cookie_to_storage_state.py` で変換した中身） |
| `POSTS_ENDPOINT` | Worker の `https://x-unmei-bot.<acct>.workers.dev/today` |
| `ADVANCE_ENDPOINT` | 同 `/advance` |
| `ADVANCE_TOKEN` | 任意の文字列（Worker の `ADVANCE_TOKEN` と一致させる） |

## 検証
1. Actions →「X daily post」→ **Run workflow** → `dry_run=1` → 緑を確認（取得のみ）
2. 同じく `dry_run=0` で1回だけ実行 → **@unmei_meishiki_ の最新ポストを目視** → 自動運転ON

## 正直な注意
- この `daily_run.py` はサンドボックスでは実投稿の検証ができていません（Xログイン不可）。
  Xの `data-testid` セレクタは変わりうるため、**初回は dry_run=1 → 実投稿**の順で1回確認してください。
- 本文にURLを入れると1投稿 $0.20 に跳ねます（無課金ルートの意味が消えます）。URLは本文に置かないこと。
