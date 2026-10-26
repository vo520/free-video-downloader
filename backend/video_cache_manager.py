"""
视频缓存管理器
实现缓存生命周期管理、自定义规则和自动清理机制
"""

import time
import threading
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone

try:
    from video_cache_db import video_cache_db
    DB_ENABLED = True
except ImportError:
    DB_ENABLED = False


class CacheRuleMatcher:
    """缓存规则匹配器"""
    
    @staticmethod
    def match_url(url: str, pattern: str) -> bool:
        """匹配URL模式"""
        if not pattern:
            return True
        
        try:
            return bool(re.search(pattern, url))
        except re.error:
            return False
    
    @staticmethod
    def match_platform(platform: str, rule_platform: str) -> bool:
        """匹配平台"""
        if not rule_platform:
            return True
        # 数据库字段可能为 NULL（None），需兜底为空串
        return (platform or "").lower() == rule_platform.lower()
    
    @staticmethod
    def match_duration(duration: float, min_dur: float, max_dur: float) -> bool:
        """匹配时长范围"""
        if min_dur and duration < min_dur:
            return False
        if max_dur and duration > max_dur:
            return False
        return True
    
    @staticmethod
    def match_quality(quality: str, rule_quality: str) -> bool:
        """匹配视频质量"""
        if not rule_quality:
            return True
        return (quality or "").lower() == rule_quality.lower()


class VideoCacheManager:
    """
    视频缓存管理器
    负责缓存生命周期管理、规则匹配和自动清理
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.db = video_cache_db if DB_ENABLED else None
        self.rule_matcher = CacheRuleMatcher()
        self._hot_cache_threshold = 100
        self._cleanup_interval = 3600
        self._last_cleanup = time.time()
        
        self._initialized = True
    
    def get_cache_ttl(self, url: str, platform: str, quality: str, duration: float) -> int:
        """
        根据缓存规则获取TTL
        
        Args:
            url: 视频URL
            platform: 平台名称
            quality: 视频质量
            duration: 视频时长（秒）
        
        Returns:
            TTL秒数
        """
        if not self.db:
            return 86400
        
        try:
            rules = self.db.get_cache_rules()
            
            matched_rule = None
            for rule in rules:
                if not rule.get('is_active'):
                    continue
                
                if not self.rule_matcher.match_platform(platform, rule.get('platform', '')):
                    continue
                
                if not self.rule_matcher.match_url(url, rule.get('url_pattern', '')):
                    continue
                
                if not self.rule_matcher.match_quality(quality, rule.get('quality', '')):
                    continue
                
                if not self.rule_matcher.match_duration(
                    duration,
                    rule.get('min_duration', 0),
                    rule.get('max_duration', 0)
                ):
                    continue
                
                if matched_rule is None or rule.get('priority', 0) > matched_rule.get('priority', 0):
                    matched_rule = rule
            
            if matched_rule:
                return matched_rule.get('ttl_seconds', 86400)
            
            return 86400
        
        except Exception as e:
            print(f"获取缓存TTL失败: {e}")
            return 86400
    
    def should_mark_as_hot(self, url: str, hit_count: int = 0) -> bool:
        """
        判断是否应该标记为热门缓存
        
        Args:
            url: 视频URL
            hit_count: 当前命中次数
        
        Returns:
            是否应该标记为热门
        """
        if not self.db:
            return False
        
        try:
            video = self.db.get_video(url)
            if not video:
                return False
            
            cache_hit_count = video.get('cache_hit_count', 0) + (hit_count if hit_count > 0 else 0)
            
            if cache_hit_count >= self._hot_cache_threshold:
                return True
            
            return False
        
        except Exception:
            return False
    
    def process_cache_hit(self, url: str):
        """
        处理缓存命中
        增加命中计数，可能标记为热门
        
        Args:
            url: 视频URL
        """
        if not self.db:
            return
        
        try:
            self.db.increment_hit_count(url)
            
            if self.should_mark_as_hot(url):
                self.db.mark_as_hot(url)
        
        except Exception as e:
            print(f"处理缓存命中失败: {e}")
    
    def auto_cleanup_expired(self, force: bool = False) -> int:
        """
        自动清理过期缓存
        
        Args:
            force: 是否强制清理
        
        Returns:
            清理的缓存数量
        """
        if not self.db:
            return 0
        
        current_time = time.time()
        if not force and (current_time - self._last_cleanup) < self._cleanup_interval:
            return 0
        
        try:
            count = self.db.cleanup_expired()
            self._last_cleanup = current_time
            print(f"自动清理过期缓存: {count} 条")
            return count
        
        except Exception as e:
            print(f"自动清理过期缓存失败: {e}")
            return 0
    
    def validate_cache(self, url: str) -> Dict[str, Any]:
        """
        验证缓存有效性
        
        Args:
            url: 视频URL
        
        Returns:
            验证结果字典
        """
        if not self.db:
            return {
                "valid": False,
                "reason": "数据库未启用"
            }
        
        try:
            video = self.db.get_video(url)
            
            if not video:
                return {
                    "valid": False,
                    "reason": "缓存不存在"
                }
            
            if video.get('cache_status') == 'expired':
                return {
                    "valid": False,
                    "reason": "缓存已过期"
                }
            
            if video.get('parse_success') == 0:
                return {
                    "valid": False,
                    "reason": "解析失败"
                }
            
            return {
                "valid": True,
                "reason": "缓存有效",
                "cache_status": video.get('cache_status'),
                "hit_count": video.get('cache_hit_count', 0),
                "is_hot": bool(video.get('is_hot')),
                "expires_at": video.get('cache_expires_at')
            }
        
        except Exception as e:
            return {
                "valid": False,
                "reason": f"验证失败: {str(e)}"
            }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        if not self.db:
            return {}
        
        try:
            stats = self.db.get_stats()
            
            total = stats.get('total_videos', 0)
            active = stats.get('active_cache', 0)
            hot = stats.get('hot_cache', 0)
            
            return {
                "total_videos": total,
                "active_cache": active,
                "expired_cache": stats.get('expired_cache', 0),
                "hot_cache": hot,
                "total_hits": stats.get('total_cache_hits', 0),
                "hit_rate": round(stats.get('total_cache_hits', 0) / max(total, 1) * 100, 2),
                "hot_rate": round(hot / max(active, 1) * 100, 2),
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            print(f"获取缓存统计失败: {e}")
            return {}
    
    def refresh_cache(self, url: str, new_ttl: Optional[int] = None) -> bool:
        """
        刷新缓存
        
        Args:
            url: 视频URL
            new_ttl: 新的TTL，如果为None则使用规则配置的TTL
        
        Returns:
            是否成功
        """
        if not self.db:
            return False
        
        try:
            video = self.db.get_video(url)
            if not video:
                return False
            
            if new_ttl is None:
                new_ttl = self.get_cache_ttl(
                    url,
                    video.get('platform', ''),
                    video.get('quality', ''),
                    video.get('duration', 0)
                )
            
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=new_ttl)
            self.db.update_cache_status(url, 'active', expires_at.isoformat())
            
            return True
        
        except Exception as e:
            print(f"刷新缓存失败: {e}")
            return False
    
    def get_lifecycle_report(self) -> Dict[str, Any]:
        """
        获取缓存生命周期报告
        
        Returns:
            生命周期报告
        """
        if not self.db:
            return {}
        
        try:
            stats = self.get_cache_stats()
            
            recent_videos = self.db.get_videos(limit=100)
            
            by_age = {
                "lt_1d": 0,
                "1d_7d": 0,
                "7d_30d": 0,
                "gt_30d": 0
            }
            
            # 必须用 UTC tz：created_at 由 save_video 写入时已带 timezone.utc，
            # naive datetime 减 aware datetime 会抛 TypeError，本应被 try/except 兜底跳过，
            # 实际导致整批 by_age 计数偏差。统一用 tz-aware 比对。
            now = datetime.now(timezone.utc)
            
            for video in recent_videos:
                try:
                    created_at = datetime.fromisoformat(video.get('created_at', now.isoformat()))
                    age_days = (now - created_at).days
                    
                    if age_days < 1:
                        by_age["lt_1d"] += 1
                    elif age_days < 7:
                        by_age["1d_7d"] += 1
                    elif age_days < 30:
                        by_age["7d_30d"] += 1
                    else:
                        by_age["gt_30d"] += 1
                except Exception:
                    continue
            
            rules = self.db.get_cache_rules()
            active_rules = [r for r in rules if r.get('is_active')]
            
            return {
                "overview": stats,
                "by_age": by_age,
                "rules_summary": {
                    "total": len(rules),
                    "active": len(active_rules)
                },
                "recommendations": self._generate_recommendations(stats, by_age),
                "timestamp": datetime.now().isoformat()
            }
        
        except Exception as e:
            print(f"生成生命周期报告失败: {e}")
            return {}
    
    def _generate_recommendations(self, stats: Dict, by_age: Dict) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        if stats.get('expired_cache', 0) > stats.get('active_cache', 0) * 0.3:
            recommendations.append("建议立即清理过期缓存，当前过期缓存比例较高")
        
        if stats.get('hot_cache', 0) == 0 and stats.get('active_cache', 0) > 20:
            recommendations.append("建议标记热门缓存以提升访问速度")
        
        if by_age.get("gt_30d", 0) > by_age.get("lt_1d", 0) * 2:
            recommendations.append("建议优化缓存规则，考虑缩短长龄缓存的TTL")
        
        if stats.get('total_videos', 0) > 1000:
            recommendations.append("缓存数据量较大，建议定期归档历史数据")
        
        if not recommendations:
            recommendations.append("缓存系统运行良好，继续保持")
        
        return recommendations


video_cache_manager = VideoCacheManager()
