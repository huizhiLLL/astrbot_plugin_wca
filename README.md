# astrbot_plugin_wca

WCA 成绩查询与 PK 插件。基于 WCA 官方 TSV 自动下载并构建本地 SQLite，支持按 WCA ID/姓名查询，PK 对比，定时更新。

## 功能
- 自动下载/更新 WCA TSV → 本地 `wca_data.db`，支持定时（默认 12 小时检查一次）
- 成绩查询：最佳单次/平均，WR/CR/NR（前 200 显示）
- PK 对比：两位选手单次与平均逐项比较，标注优势项 (☆)，统计总分 (★)

## 指令
- `/wca <WCA ID 或姓名>` 查询单人成绩
- `/wcapk <选手1> <选手2>` PK 对比（WCA ID 或唯一姓名）
- `/wca更新` 强制重新下载并重建数据库

## 依赖
- aiohttp
- pandas
