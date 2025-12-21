# astrbot_plugin_wca

WCA 成绩查询与 PK 插件。基于 WCA 官方 TSV 自动下载并构建本地 SQLite，支持按 WCA ID/姓名查询，PK 对比，定时更新。

**当前版本：v1.0.4**

## 功能

- **自动更新**：自动下载/更新 WCA TSV → 本地持久化数据 `data/plugin_data/astrbot_plugin_wca/wca_data.db`，支持定时（默认 12 小时检查一次）
- **WCA v2 适配**：已适配 WCA 官方 v2 导出格式（snake_case 表名和字段名）
- **成绩查询**：WCA 官方成绩查询，最佳单次/平均，WR/CR/NR（前 200 显示）
- **PK 对比**：两位选手单次与平均逐项比较，标注优势项 (☆/★)，统计总分 (⭐)
- **宿敌查询**：统计在共同项目中"单次与平均均优于你"的选手数量（世界/洲/地区），人数少于等于 5 时会列出名单
- **近期比赛**：通过 cubing.com API 获取近期在中国举办的 WCA 比赛列表

## 指令

- `/wca <WCA ID 或姓名>` - 查询个人最佳成绩
- `/wcapk <选手1> <选手2>` - PK 对比（WCA ID 或唯一姓名）
- `/wca更新` - 强制重新下载并重建数据库
- `/宿敌 <WCA ID 或姓名>` - 查询宿敌
- `/近期比赛` - 查询近期在中国举办的 WCA 比赛（最近 6 个月）

## 依赖

- pandas

## 更新日志

### v1.0.4

- **WCA v2 数据库适配**：适配 WCA 官方 v2 导出格式，支持新的 snake_case 表名和字段名（如 `persons.wca_id`、`persons.country_id` 等）
- **近期比赛功能**：新增 `/近期比赛` 命令，通过 cubing.com API 获取近期在中国举办的 WCA 比赛列表，显示中文比赛名称和地点信息

### v1.0.3

- 修复宿敌查询条件判断的 bug

### v1.0.2

- 修复宿敌查询中洲人数和世界人数一致的 bug
- 数据库存储路径规范为 `data/plugin_data/astrbot_plugin_wca/`

### v1.0.1

- **数据持久化改进**：使用 `StarTools.get_data_dir()` 将数据文件存储在规范的 `data/plugin_data/wca/` 目录，而不是插件源代码目录
- **性能优化**：使用 `asyncio.to_thread()` 将 TSV 处理操作放入线程池执行，避免阻塞主事件循环
- **代码重构**：将 `process_tsv_to_sqlite()` 方法拆分为多个专用辅助函数，提高代码可读性和可维护性
- **宿敌查询**：新增了宿敌查询功能

### v1.0.0

- 初始版本

## 效果图

<img src="https://cdn.jsdelivr.net/gh/huizhiLLL/Photo-bed@main/img/PixPin_2025-12-13_20-52-28.png" style="zoom:50%;" >

<img src="https://cdn.jsdelivr.net/gh/huizhiLLL/Photo-bed@main/img/PixPin_2025-12-13_20-53-07.png" style="zoom:40%;" >
