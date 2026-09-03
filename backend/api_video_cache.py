"""
视频缓存管理API
提供视频缓存数据的增删改查、实时监控和运维管理功能
"""

import json
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from auth import get_current_user

router = APIRouter(
    prefix="/api/video-cache",
    tags=["视频缓存管理"],
    # B17：视频缓存接口全部要求登录，禁止匿名读取/删除/导出/清理缓存与解析日志。
    dependencies=[Depends(get_current_user)],
)

try:
    from video_cache_db import video_cache_db
    from video_cache_manager import video_cache_manager
    DB_ENABLED = True
except ImportError:
    DB_ENABLED = False
    print("警告: 视频缓存数据库未启用")


# ===== 请求模型 =====

def _csv_safe(v):
    """防止 CSV 公式注入：以 = + - @ 或制表/回车开头的单元格前缀单引号，
    避免管理员在 Excel 打开导出文件时误执行恶意公式（数据外泄/钓鱼）。"""
    s = "" if v is None else str(v)
    return ("'" + s) if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s

class SaveVideoRequest(BaseModel):
    url: str
    video_info: dict
    metadata: dict
    success: bool = True
    error: Optional[str] = None


class UpdateCacheStatusRequest(BaseModel):
    url: str
    status: str
    expires_at: Optional[str] = None


class SaveCacheRuleRequest(BaseModel):
    rule_name: str
    rule_type: str
    platform: Optional[str] = None
    url_pattern: Optional[str] = None
    quality: Optional[str] = None
    min_duration: Optional[float] = None
    max_duration: Optional[float] = None
    ttl_seconds: int = 86400
    priority: int = 0
    is_active: bool = True
    description: Optional[str] = None


class SaveParseLogRequest(BaseModel):
    url: str
    task_id: str
    status: str
    progress: int = 0
    stage: Optional[str] = None
    message: Optional[str] = None
    success: bool = False
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: int = 0
    retry_count: int = 0


# ===== 缓存数据API =====

@router.get("/videos")
async def get_videos(
    cache_status: Optional[str] = Query(None, description="缓存状态筛选"),
    platform: Optional[str] = Query(None, description="平台筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    hot_only: bool = Query(False, description="仅热门缓存"),
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """获取视频缓存列表"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        videos = video_cache_db.get_videos(
            cache_status=cache_status,
            platform=platform,
            search=search,
            hot_only=hot_only,
            limit=limit,
            offset=offset
        )
        
        return JSONResponse(content={
            "success": True,
            "data": videos,
            "total": len(videos),
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/videos/{url:path}")
async def get_video(url: str):
    """获取单个视频缓存详情"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        video = video_cache_db.get_video(url)
        if not video:
            raise HTTPException(status_code=404, detail="视频缓存不存在")
        
        video_cache_db.increment_hit_count(url)
        
        return JSONResponse(content={
            "success": True,
            "data": video
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/videos")
async def save_video(req: SaveVideoRequest):
    """保存视频缓存数据"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        video_data = {
            "url": req.url,
            "video_info": req.video_info,
            "metadata": req.metadata,
            "success": req.success,
            "error": req.error
        }
        
        success = video_cache_db.save_video(video_data)

        # 接通 video_cache_manager：每次保存后按内置节流(默认 1h)自动清理过期缓存，
        # 避免过期条目无限堆积。best-effort，失败不影响保存主流程。
        try:
            video_cache_manager.auto_cleanup_expired()
        except Exception:
            pass

        return JSONResponse(content={
            "success": success,
            "message": "视频缓存保存成功" if success else "视频缓存保存失败"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/videos/status")
async def update_cache_status(req: UpdateCacheStatusRequest):
    """更新视频缓存状态"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        video_cache_db.update_cache_status(req.url, req.status, req.expires_at)
        
        return JSONResponse(content={
            "success": True,
            "message": "缓存状态更新成功"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/videos/{url:path}")
async def delete_video(url: str):
    """删除视频缓存"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        success = video_cache_db.delete_video(url)
        
        if not success:
            raise HTTPException(status_code=404, detail="视频缓存不存在")
        
        return JSONResponse(content={
            "success": True,
            "message": "视频缓存删除成功"
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/videos/{url:path}/hot")
async def mark_video_hot(url: str):
    """标记为热门缓存"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        video_cache_db.mark_as_hot(url)
        
        return JSONResponse(content={
            "success": True,
            "message": "已标记为热门缓存"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== 统计信息API =====

@router.get("/stats")
async def get_cache_stats():
    """获取缓存统计信息"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        stats = video_cache_db.get_stats()
        
        return JSONResponse(content={
            "success": True,
            "data": stats
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup")
async def cleanup_expired_cache():
    """清理过期缓存"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        count = video_cache_db.cleanup_expired()
        
        return JSONResponse(content={
            "success": True,
            "message": f"已清理 {count} 条过期缓存"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== 缓存规则API =====

@router.get("/rules")
async def get_cache_rules():
    """获取缓存规则列表"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        rules = video_cache_db.get_cache_rules()
        
        return JSONResponse(content={
            "success": True,
            "data": rules
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules")
async def save_cache_rule(req: SaveCacheRuleRequest):
    """保存缓存规则"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        rule_data = req.model_dump()
        success = video_cache_db.save_cache_rule(rule_data)
        
        return JSONResponse(content={
            "success": success,
            "message": "缓存规则保存成功" if success else "缓存规则保存失败"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules/{rule_name}")
async def delete_cache_rule(rule_name: str):
    """删除缓存规则"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        success = video_cache_db.delete_cache_rule(rule_name)
        
        if not success:
            raise HTTPException(status_code=404, detail="缓存规则不存在")
        
        return JSONResponse(content={
            "success": True,
            "message": "缓存规则删除成功"
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== 解析日志API =====

@router.get("/logs")
async def get_parse_logs(limit: int = Query(100, ge=1, le=500)):
    """获取解析任务日志"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        logs = video_cache_db.get_parse_logs(limit=limit)
        
        return JSONResponse(content={
            "success": True,
            "data": logs,
            "total": len(logs)
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logs")
async def save_parse_log(req: SaveParseLogRequest):
    """保存解析日志"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        log_data = req.model_dump()
        success = video_cache_db.save_parse_log(log_data)
        
        return JSONResponse(content={
            "success": success,
            "message": "解析日志保存成功" if success else "解析日志保存失败"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== 实时监控API =====

@router.get("/monitor/status")
async def get_monitor_status():
    """获取实时监控状态"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        stats = video_cache_db.get_stats()
        recent_logs = video_cache_db.get_parse_logs(limit=20)
        
        total_logs = len(recent_logs)
        success_count = sum(1 for log in recent_logs if log.get('success'))
        failed_count = total_logs - success_count
        success_rate = (success_count / total_logs * 100) if total_logs > 0 else 0
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "cache_stats": stats,
                "monitor_stats": {
                    "total_tasks": total_logs,
                    "successful_tasks": success_count,
                    "failed_tasks": failed_count,
                    "success_rate": round(success_rate, 2),
                    "timestamp": datetime.now().isoformat()
                },
                "recent_logs": recent_logs
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitor/health")
async def get_system_health():
    """获取系统健康状态"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        stats = video_cache_db.get_stats()
        
        health_score = 100
        issues = []
        
        if stats['expired_cache'] > stats['active_cache'] * 0.5:
            health_score -= 20
            issues.append("过期缓存比例过高")
        
        if stats['hot_cache'] == 0 and stats['active_cache'] > 10:
            health_score -= 10
            issues.append("缺少热门缓存标记")
        
        health_status = "healthy"
        if health_score < 80:
            health_status = "warning"
        if health_score < 60:
            health_status = "critical"
        
        return JSONResponse(content={
            "success": True,
            "data": {
                "health_score": max(0, health_score),
                "health_status": health_status,
                "issues": issues,
                "recommendations": [
                    "定期清理过期缓存" if stats['expired_cache'] > 0 else "缓存状态良好",
                    "热门视频自动续期功能运行正常" if stats['hot_cache'] > 0 else "建议增加热门视频缓存"
                ],
                "timestamp": datetime.now().isoformat()
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===== 导出API =====

@router.get("/export")
async def export_cache_data(
    format: str = Query("json", pattern="^(json|csv)$"),
    cache_status: Optional[str] = Query(None),
    platform: Optional[str] = Query(None)
):
    """导出缓存数据"""
    if not DB_ENABLED:
        raise HTTPException(status_code=503, detail="数据库未启用")
    
    try:
        videos = video_cache_db.get_videos(
            cache_status=cache_status,
            platform=platform,
            limit=10000
        )
        
        if format == "json":
            content = json.dumps(videos, ensure_ascii=False, indent=2)
            media_type = "application/json"
            filename = f"video_cache_export_{int(time.time())}.json"
        else:
            if not videos:
                videos = []

            # 使用标准库 csv 模块生成，正确转义标题中的逗号/引号/换行，避免 CSV 注入与格式损坏。
            import io as _io
            import csv as _csv
            buf = _io.StringIO()
            writer = _csv.writer(buf)
            writer.writerow(["URL", "平台", "标题", "时长", "文件大小", "缓存状态", "访问次数", "最后访问"])
            for v in videos:
                writer.writerow([
                    _csv_safe(v.get("video_url", "")),
                    _csv_safe(v.get("platform", "")),
                    _csv_safe(v.get("title", "")),
                    v.get("duration", 0),
                    v.get("file_size", 0),
                    v.get("cache_status", ""),
                    v.get("cache_hit_count", 0),
                    v.get("last_access_at", ""),
                ])
            content = buf.getvalue()
            media_type = "text/csv"
            filename = f"video_cache_export_{int(time.time())}.csv"
        
        return StreamingResponse(
            iter([content]),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
