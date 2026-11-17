# Work 模式接手指南｜KKL Bioenergy

## 使用前先區分兩套資料

**公開 Repo（本專案）**：已發布的簡化 SVG／GeoJSON、分層網站、環評建模基準及各版 QA 報告。

**私有交接包（本 Repo 不含此檔）**：`KKL_Work_Handoff_PRIVATE_V0.9.9.zip`。由使用者在 Work 對話中另外上傳。包含使用者提供的 `C04.PDF`、從 PDF 直接擷取的原始向量 SVG／DXF、原始 Python 試驗腳本、原始圖面疊圖與來源線段記錄。**不可將整包 ZIP、原始 PDF 或全量原始向量提交至公開 Repo 或部署至 GitHub Pages**；先確認公開散布／重製權限。

## Work 模式任務

1. 讀取本 Repo 的 `README.md`、`docs/V0.9-EIA-modeling-baseline.md`、`docs/V0.9.8-fountain-curve-vector-QA.md`、`docs/V0.9.9-source-fragment-connectivity.md`。
2. 從使用者上傳的私有 ZIP，讀取 `README.md`、`docs/WORK_TASK.md`、`docs/REPRODUCIBILITY.md`、`docs/ASSET_MANIFEST.json`。
3. 以 ZIP 中的 `source/C04.PDF`（**PDF 第 7、8 頁**）為主資料。所有資料不得直接當 2026 年現況或施工圖。
4. 把舊有硬編碼 `/mnt/data/` 路徑的分析腳本整理成具參數的 CLI，並建立測試與結果重現流程。
5. 優先以原始 PDF 向量線段追蹤可確認的建築、道路、水景輪廓；V0.9.9 的水景 **0 條經驗證閉合輪廓**，不得假裝已完成。對候選記錄來源線段 ID、幾何殘差、拓樸 QA、精度等級。
6. 以原圖比例尺進行校核，再建立環評歷史 2D 底圖，保留既有／擴建區層別。歷史計畫總面積 **204,820 m²**；不得使用先前 Google Maps 粗選的 282,716.95 m² 當作工程比例尺。
7. 在開發分支交付變更，透過 Pull Request 提供圖面對照、單元測試、QA 清單及 GitHub Pages 預覽。**2D 圖層驗收之前不要直接進行寫實 3D 建模。**

## 建議輸出

- Python 可重現 pipeline（支援輸入路徑、頁碼、裁切範圍與輸出）。
- 來源圖層分類與可編輯向量資料、保留來源索引及不確定性。
- 圖 4.2.2-1 和 4.2.2-2 的同基準對位報告。
- PDF 原圖與重建圖的 QA 疊圖（公開時注意來源圖資授權）。
- 明確標示已確認、待人工複核及未辨識地物的分層網站。

## 不可忽略的限制

- PDF 具有大量向量路徑，但原始 CAD Layer、Block 及工程座標未被完整復原。
- 圖面暫定換算 0.51724 m／圖面像素，**尚未經完整比例尺／座標控制點校核**。
- 早期手描水景曲線與 PDF 原向量比對不通過，不能作為精確 CAD。
- 本專案原始檔案的公開散布權限未確認，請用私有資料工作區處理。

_本文件刻意不包含原始 PDF 或其完整向量內容。_
