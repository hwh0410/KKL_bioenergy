# KKL Bioenergy｜金門酒廠金寧廠 3D 廠區平台

以 Three.js 與 GitHub Pages 製作的互動式廠區模型，先建立既有廠區量體，後續用於規劃厭氧沼氣設施（AD）配置、工程量體與概念方案比較。

## 網站
預期 Pages 網址（須在 Settings → Pages 啟用 GitHub Actions，且帳號方案支援）：https://hwh0410.github.io/KKL_bioenergy/

## V0.1 功能
- 廠區 3D 量體、代表性入口地標、道路與植栽
- 立體／俯視切換、拖曳旋轉、平移、縮放
- 點擊量體查看示意資訊
- 建築標籤、道路／植栽開關、PNG 截圖
- 自動部署 GitHub Pages workflow

## 資料精度
**V0.1 是示意概念場景，不是實際測繪成果。** 建築尺寸、位置、用途標示及朝向都需要在取得正射影像、廠區配置圖與照片後校核；目前不能作為距離或工程決策的依據。

## 開發路線
1. **V0.2：現況校核** — 取得正射影像或空拍，建立座標底圖與建築外框。
2. **V0.3：現況量體** — 建築高度、屋頂型式、道路與主要設施校正。
3. **V0.4：圖層管理** — 分離既有設施和規劃設施的資料與顯示。
4. **V1.0：厭氧沼氣規劃** — 新增反應槽、預處理、沼氣儲存、公用設施與動線的方案比較（需符合實際工程條件）。

## 技術
純靜態 HTML + Three.js（透過 jsDelivr 載入），不需伺服器或後端。部署採用 `.github/workflows/deploy-pages.yml`，Push 到 main 後執行。

## 開啟 GitHub Pages
在 GitHub Repository 的 **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。請留意此 Repository 如為 private，GitHub Pages 是否可用與方案權限有關；不能使用時可調整可見性或方案，先確認沒有不適合公開的資料。
