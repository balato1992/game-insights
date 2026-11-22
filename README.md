# game-insights

每週三 07:30（台北時間）自動抓取 Steam 公開商店資料，追蹤各遊戲類型的供給量與成功率，作為選題與行銷決策的參考。

## 產出

- `reports/LATEST.md`：最新一週的報告（各類型成功率、近 90 天新作供給、近期最熱門新作、售價與成功率）
- `reports/<日期>.md`：歷史週報
- `data/<日期>/tag_summary.csv`：各類型彙總數字
- `data/<日期>/games.csv.gz`：每款遊戲的原始紀錄（appid、名稱、上市日、評論數、好評率、售價、標籤、分組）

## 方法

- 資料來源：`store.steampowered.com/search/results`，按上市日排序，逐頁讀取。
- 成熟期分組：上市 365–730 天前的遊戲，評論已累積一年。成功率 = 評論數 ≥ 1,000 的比例（以約 35 套 / 則評論換算，約 3.5 萬套）。
- 近期分組：近 90 天上市的遊戲，用來看新作供給與正在起量的作品。
- 推薦排序：以「≥100 評論比例 ÷ 全體平均」為基礎分數，`config/preferences.json` 裡的偏好類型乘上加權（預設 1.3）。偏好只加分、不過濾，所有類型都會列出。
- 追蹤的標籤列在 `config/tags.json`，可自行增減（數字是 Steam 標籤 ID，可從 `https://store.steampowered.com/tagdata/populartags/english` 查詢）。

## 排程

`.github/workflows/weekly-steam-snapshot.yml`，每週二 23:30 UTC 執行；也可在 Actions 頁面手動按 **Run workflow**。Steam 有流量限制，一次約需 20–60 分鐘。

## 限制

- Steam 標籤是玩家貼的，熱門遊戲較容易被貼上小眾標籤，樣本小的標籤成功率會被高估。
- 成功的遊戲包含 AA 大作；售價是抓取當天價格，可能含折扣。
