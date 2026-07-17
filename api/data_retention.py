"""
数据保留策略：自动归档与定期清理
"""
from db import get_db


def archive_old_records(retention_days: int = 30) -> int:
    """
    将超过 retention_days 天的数据从主表移动到归档表。
    返回归档的记录数。
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # 1. 将旧数据复制到归档表
                cur.execute("""
                    INSERT INTO cost_records_archive 
                        (user_name, thread_id, model, purpose, prompt_tokens, completion_tokens,
                         total_tokens, input_cost, output_cost, total_cost, tool_name, tool_args, created_at)
                    SELECT user_name, thread_id, model, purpose, prompt_tokens, completion_tokens,
                           total_tokens, input_cost, output_cost, total_cost, tool_name, tool_args, created_at
                    FROM cost_records
                    WHERE created_at < CURRENT_DATE - %s;
                """, (retention_days,))
                
                archived_count = cur.rowcount
                
                # 2. 从主表删除已归档的数据
                cur.execute("""
                    DELETE FROM cost_records
                    WHERE created_at < CURRENT_DATE - %s;
                """, (retention_days,))
                
                conn.commit()
                return archived_count
    except Exception as e:
        print(f"[DataRetention] 归档失败: {e}")
        return 0


def delete_expired_records(expiration_days: int = 365) -> int:
    """
    删除归档表中超过 expiration_days 天的记录。
    返回删除的记录数。
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM cost_records_archive
                    WHERE created_at < CURRENT_DATE - %s;
                """, (expiration_days,))
                
                deleted_count = cur.rowcount
                conn.commit()
                return deleted_count
    except Exception as e:
        print(f"[DataRetention] 清理过期数据失败: {e}")
        return 0


def run_retention_task():
    """
    执行一次完整的数据保留任务。
    返回 (归档数, 清理数)
    """
    archived = archive_old_records(retention_days=30)
    deleted = delete_expired_records(expiration_days=365)
    
    if archived > 0 or deleted > 0:
        print(f"[DataRetention] 归档 {archived} 条，清理 {deleted} 条")
    
    return archived, deleted