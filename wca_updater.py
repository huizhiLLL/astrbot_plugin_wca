import asyncio
import json
import sqlite3
import zipfile
import tempfile
from pathlib import Path
from typing import Optional
import aiohttp
import pandas as pd
from astrbot.api import logger

WCA_EXPORT_API = "https://www.worldcubeassociation.org/api/v0/export/public"
REQUEST_TIMEOUT = 600  # 10分钟超时（下载和处理 TSV 可能需要较长时间）
CHUNKSIZE = 10000  # Pandas 分批读取的行数


class WCAUpdater:
    """WCA 数据库更新器"""
    
    def __init__(self, db_path: str | Path):
        """
        Args:
            db_path: SQLite 数据库文件保存路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_session(self):
        """确保 HTTP session 存在"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def close(self):
        """关闭 session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_export_info(self) -> Optional[dict]:
        """获取 WCA 导出信息
        
        Returns:
            导出信息字典，包含 sql_url 和 tsv_url 等
        """
        session = await self._ensure_session()
        
        try:
            async with session.get(WCA_EXPORT_API) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"获取 WCA 导出信息失败，状态码：{response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"获取 WCA 导出信息超时（{REQUEST_TIMEOUT}秒）")
            return None
        except Exception as e:
            logger.error(f"获取 WCA 导出信息异常: {e}")
            return None
    
    async def download_tsv_archive(self, tsv_url: str, progress_callback=None) -> Optional[Path]:
        """下载 TSV 压缩包文件
        
        Args:
            tsv_url: TSV 压缩包下载 URL
            progress_callback: 可选的回调函数，用于报告下载进度
        
        Returns:
            下载的临时文件路径，如果失败则返回 None
        """
        session = await self._ensure_session()
        
        try:
            logger.info(f"开始下载 WCA TSV 压缩包: {tsv_url}")
            
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            temp_path = Path(temp_file.name)
            temp_file.close()
            
            async with session.get(tsv_url) as response:
                if response.status != 200:
                    logger.error(f"下载 WCA TSV 压缩包失败，状态码：{response.status}")
                    temp_path.unlink(missing_ok=True)
                    return None
                
                # 获取文件大小（如果可用）
                total_size = response.headers.get('Content-Length')
                if total_size:
                    total_size = int(total_size)
                    logger.info(f"TSV 压缩包大小: {total_size / 1024 / 1024:.2f} MB")
                
                # 下载并保存文件
                downloaded = 0
                with open(temp_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size:
                            progress = downloaded / total_size * 100
                            progress_callback(progress)
                
                logger.info(f"WCA TSV 压缩包下载完成: {temp_path}")
                return temp_path
                
        except asyncio.TimeoutError:
            logger.error(f"下载 WCA TSV 压缩包超时（{REQUEST_TIMEOUT}秒）")
            temp_path.unlink(missing_ok=True)
            return None
        except Exception as e:
            logger.error(f"下载 WCA TSV 压缩包异常: {e}")
            temp_path.unlink(missing_ok=True)
            return None
    
    def _find_tsv_file(self, temp_dir_path: Path, table: str) -> Path | None:
        """在解压目录中查找指定表的 TSV 文件（递归）
        
        兼容官方导出命名：WCA_export_{Table}.tsv
        也兼容纯 {Table}.tsv。
        
        Args:
            temp_dir_path: 临时目录路径
            table: 表名
        
        Returns:
            找到的 TSV 文件路径，如果未找到则返回 None
        """
        patterns = [
            f"{table}.tsv",
            f"WCA_export_{table}.tsv",
            f"{table}.TSV",
            f"WCA_export_{table}.TSV",
        ]
        for pattern in patterns:
            for path in temp_dir_path.rglob(pattern):
                if path.is_file():
                    return path
        return None
    
    def _process_single_table(self, conn: sqlite3.Connection, table_name: str, tsv_file: Path) -> bool:
        """处理单个 TSV 表文件并写入数据库
        
        Args:
            conn: SQLite 数据库连接
            table_name: 表名
            tsv_file: TSV 文件路径
        
        Returns:
            是否处理成功
        """
        try:
            logger.info(f"正在处理表: {table_name}")
            
            chunk_count = 0
            total_rows = 0
            is_first_chunk = True
            
            # 分批读取并插入数据
            for chunk in pd.read_csv(
                tsv_file,
                sep='\t',
                chunksize=CHUNKSIZE,
                encoding='utf-8',
                low_memory=False
            ):
                chunk_count += 1
                chunk_rows = len(chunk)
                total_rows += chunk_rows
                
                # 第一次读取时创建表，后续追加数据
                if is_first_chunk:
                    chunk.to_sql(
                        table_name,
                        conn,
                        if_exists='replace',
                        index=False
                    )
                    is_first_chunk = False
                else:
                    chunk.to_sql(
                        table_name,
                        conn,
                        if_exists='append',
                        index=False
                    )
                
                # 每处理一定数量的块就提交一次
                if chunk_count % 10 == 0:
                    conn.commit()
                    logger.info(
                        f"  表 {table_name}: 已处理 {chunk_count} 个数据块，"
                        f"共 {total_rows} 行"
                    )
            
            # 最终提交
            conn.commit()
            logger.info(f"表 {table_name} 处理完成: 共 {total_rows} 行数据")
            return True
            
        except Exception as e:
            logger.error(f"处理表 {table_name} 时出错: {e}")
            return False
    
    def _create_database_indexes(self, conn: sqlite3.Connection) -> None:
        """为数据库创建索引以提高查询性能
        
        Args:
            conn: SQLite 数据库连接
        """
        logger.info("正在创建索引...")
        try:
            # 为常用查询字段创建索引（存在才建）
            conn.execute("CREATE INDEX IF NOT EXISTS idx_persons_wca_id ON persons(wca_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rankssingle_person_id ON ranks_single(person_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rankssingle_event_id ON ranks_single(event_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ranksaverage_person_id ON ranks_average(person_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ranksaverage_event_id ON ranks_average(event_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_id ON events(id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_competitions_id ON competitions(id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_competitions_country_id ON competitions(country_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_competitions_start_date ON competitions(start_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_competitions_end_date ON competitions(end_date)")
            
            # 为宿敌查询优化：复合索引加速 event_id + best 的查询
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rankssingle_event_best ON ranks_single(event_id, best)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ranksaverage_event_best ON ranks_average(event_id, best)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rankssingle_event_best_person ON ranks_single(event_id, best, person_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ranksaverage_event_best_person ON ranks_average(event_id, best, person_id)")
            
            conn.commit()
            logger.info("索引创建完成")
        except Exception as e:
            logger.warning(f"创建索引时出错（可忽略）: {e}")
    
    def process_tsv_to_sqlite(self, tsv_archive_path: Path) -> bool:
        """处理 TSV 文件并转换为 SQLite 数据库
        
        Args:
            tsv_archive_path: TSV 压缩包路径
        
        Returns:
            是否处理成功
        """
        try:
            # 创建临时目录用于解压
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)
                
                logger.info("正在解压 TSV 压缩包...")
                # 解压文件
                with zipfile.ZipFile(tsv_archive_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir_path)
                
                logger.info("开始处理 TSV 文件并转换为 SQLite 数据库...")
                
                # 连接到 SQLite 数据库
                conn = sqlite3.connect(str(self.db_path))
                
                # 需要处理的表（按依赖顺序）
                required_tables = [
                    "countries",   # 先导入国家表，用于洲别映射等
                    "events",      # 赛事定义
                    "persons",     # 选手信息
                    "competitions", # 比赛信息
                    "ranks_single", # 单次排名
                    "ranks_average", # 平均排名
                ]
                
                # 处理每个表
                for table_name in required_tables:
                    tsv_file = self._find_tsv_file(temp_dir_path, table_name)
                    
                    if not tsv_file:
                        logger.warning(f"TSV 文件不存在: {table_name}.tsv")
                        continue
                    
                    if not self._process_single_table(conn, table_name, tsv_file):
                        conn.close()
                        return False
                
                # 创建索引以提高查询性能
                self._create_database_indexes(conn)
                
                conn.close()
                logger.info("TSV 文件处理完成，SQLite 数据库已创建")
                return True
                
        except Exception as e:
            logger.error(f"处理 TSV 文件时出错: {e}")
            return False
    
    async def update_database(self, force: bool = False) -> bool:
        """更新 WCA 数据库
        
        Args:
            force: 是否强制更新（即使数据库已存在）
        
        Returns:
            是否更新成功
        """
        # 检查数据库是否已存在
        if self.db_path.exists() and not force:
            # 老版本数据库可能缺少 Countries 表，验证通过才跳过下载
            if self.verify_database():
                logger.info(f"WCA 数据库已存在: {self.db_path}")
                return True
            logger.info("现有 WCA 数据库缺少必要表，准备重新下载并构建")
        
        # 获取导出信息
        export_info = await self.get_export_info()
        if not export_info:
            logger.error("无法获取 WCA 导出信息")
            return False
        
        tsv_url = export_info.get("tsv_url")
        if not tsv_url:
            logger.error("WCA 导出信息中未找到 TSV 压缩包 URL")
            return False
        
        # 下载 TSV 压缩包
        tsv_archive_path = await self.download_tsv_archive(tsv_url)
        if not tsv_archive_path:
            logger.error("下载 TSV 压缩包失败")
            return False
        
        try:
            # 处理 TSV 文件并转换为 SQLite 数据库（在线程池中执行以避免阻塞事件循环）
            success = await asyncio.to_thread(self.process_tsv_to_sqlite, tsv_archive_path)
            
            if success:
                # 验证数据库文件
                if self.verify_database():
                    logger.info("WCA 数据库更新成功并验证通过")
                    return True
                else:
                    logger.error("WCA 数据库文件验证失败")
                    return False
            
            return False
            
        finally:
            # 清理临时文件
            try:
                if tsv_archive_path.exists():
                    tsv_archive_path.unlink()
                    logger.info("已清理临时 TSV 压缩包文件")
            except Exception as e:
                logger.warning(f"清理临时文件时出错: {e}")
    
    def verify_database(self) -> bool:
        """验证数据库文件是否有效
        
        Returns:
            数据库是否有效
        """
        if not self.db_path.exists():
            return False
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 检查必要的表是否存在
            required_tables = ["persons", "events", "competitions", "ranks_single", "ranks_average", "countries"]
            placeholders = ",".join(["?"] * len(required_tables))
            cursor.execute(
                f"""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ({placeholders})
                """,
                required_tables,
            )
            
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            
            if len(existing_tables) == len(required_tables):
                logger.info("WCA 数据库验证通过")
                return True
            else:
                missing = set(required_tables) - set(existing_tables)
                logger.error(f"WCA 数据库缺少必要的表: {missing}")
                return False
                
        except Exception as e:
            logger.error(f"验证 WCA 数据库时出错: {e}")
            return False
    
    def get_database_info(self) -> Optional[dict]:
        """获取数据库信息（导出日期等）
        
        Returns:
            数据库信息字典，如果数据库不存在则返回 None
        """
        if not self.db_path.exists():
            return None
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 尝试读取 metadata 表（如果存在）
            try:
                cursor.execute("SELECT * FROM metadata")
                metadata_row = cursor.fetchone()
                if metadata_row:
                    # 假设 metadata 表有 export_date 和 export_format_version 字段
                    # 实际结构可能不同，需要根据实际情况调整
                    return dict(zip([d[0] for d in cursor.description], metadata_row))
            except sqlite3.OperationalError:
                # metadata 表不存在，尝试从其他方式获取信息
                pass
            
            # 获取数据库文件修改时间作为参考
            mtime = self.db_path.stat().st_mtime
            
            conn.close()
            
            return {
                "file_mtime": mtime,
                "file_path": str(self.db_path),
            }
            
        except Exception as e:
            logger.error(f"获取数据库信息时出错: {e}")
            return None

