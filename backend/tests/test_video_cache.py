"""
视频缓存系统测试
包括单元测试和集成测试
"""

import pytest
import time
import os
import sys
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from video_cache_db import VideoCacheDB, get_video_cache_db_path
    from video_cache_manager import VideoCacheManager
    from cache_key_generator import CacheKeyGenerator
    DB_AVAILABLE = True
except ImportError as e:
    DB_AVAILABLE = False
    print(f"数据库模块导入失败: {e}")


@pytest.fixture
def test_db():
    """创建测试用数据库"""
    if not DB_AVAILABLE:
        pytest.skip("数据库模块不可用")
    
    test_db_path = os.path.join(os.path.dirname(__file__), "test_video_cache.db")
    
    import video_cache_db
    original_path = video_cache_db.VIDEO_CACHE_DB_PATH
    video_cache_db.VIDEO_CACHE_DB_PATH = test_db_path
    
    db = VideoCacheDB()
    yield db
    
    db._initialized = False
    video_cache_db.VIDEO_CACHE_DB_PATH = original_path
    
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


class TestVideoCacheDB:
    """视频缓存数据库测试"""
    
    def test_save_video(self, test_db):
        """测试保存视频数据"""
        video_data = {
            "url": "https://www.youtube.com/watch?v=test123",
            "video_info": {
                "platform": "youtube",
                "video_id": "test123",
                "title": "测试视频",
                "uploader": "测试用户",
                "thumbnail": "https://example.com/thumb.jpg"
            },
            "metadata": {
                "duration": 180.5,
                "width": 1920,
                "height": 1080,
                "file_size": 104857600,
                "format": "mp4",
                "quality": "1080p"
            },
            "success": True
        }
        
        result = test_db.save_video(video_data)
        assert result == True
        
        saved_video = test_db.get_video("https://www.youtube.com/watch?v=test123")
        assert saved_video is not None
        assert saved_video['title'] == "测试视频"
        assert saved_video['platform'] == "youtube"
        assert saved_video['duration'] == 180.5
    
    def test_get_video_not_found(self, test_db):
        """测试获取不存在的视频"""
        video = test_db.get_video("https://nonexistent.com/video")
        assert video is None
    
    def test_get_videos(self, test_db):
        """测试获取视频列表"""
        for i in range(5):
            test_db.save_video({
                "url": f"https://test.com/video{i}",
                "video_info": {"platform": "youtube", "title": f"视频{i}"},
                "metadata": {},
                "success": True
            })
        
        videos = test_db.get_videos()
        assert len(videos) >= 5
    
    def test_get_videos_with_filter(self, test_db):
        """测试带筛选的查询"""
        test_db.save_video({
            "url": "https://youtube.com/video1",
            "video_info": {"platform": "youtube", "title": "YouTube视频"},
            "metadata": {},
            "success": True
        })
        
        test_db.save_video({
            "url": "https://bilibili.com/video1",
            "video_info": {"platform": "bilibili", "title": "B站视频"},
            "metadata": {},
            "success": True
        })
        
        youtube_videos = test_db.get_videos(platform="youtube")
        assert all(v['platform'] == 'youtube' for v in youtube_videos)
    
    def test_update_cache_status(self, test_db):
        """测试更新缓存状态"""
        test_db.save_video({
            "url": "https://test.com/status",
            "video_info": {},
            "metadata": {},
            "success": True
        })
        
        test_db.update_cache_status("https://test.com/status", "expired")
        
        video = test_db.get_video("https://test.com/status")
        assert video['cache_status'] == "expired"
    
    def test_increment_hit_count(self, test_db):
        """测试增加命中计数"""
        test_db.save_video({
            "url": "https://test.com/hits",
            "video_info": {},
            "metadata": {},
            "success": True
        })
        
        test_db.increment_hit_count("https://test.com/hits")
        test_db.increment_hit_count("https://test.com/hits")
        
        video = test_db.get_video("https://test.com/hits")
        assert video['cache_hit_count'] == 2
    
    def test_delete_video(self, test_db):
        """测试删除视频"""
        test_db.save_video({
            "url": "https://test.com/delete",
            "video_info": {},
            "metadata": {},
            "success": True
        })
        
        result = test_db.delete_video("https://test.com/delete")
        assert result == True
        
        video = test_db.get_video("https://test.com/delete")
        assert video is None
    
    def test_get_stats(self, test_db):
        """测试获取统计信息"""
        test_db.save_video({
            "url": "https://test.com/stats",
            "video_info": {"platform": "youtube"},
            "metadata": {},
            "success": True
        })
        
        stats = test_db.get_stats()
        assert 'total_videos' in stats
        assert stats['total_videos'] >= 1
        assert 'by_platform' in stats


class TestParseLogs:
    """解析日志测试"""
    
    def test_save_parse_log(self, test_db):
        """测试保存解析日志"""
        log_data = {
            "url": "https://test.com/log",
            "task_id": "task123",
            "status": "success",
            "progress": 100,
            "success": True,
            "duration_ms": 1500
        }
        
        result = test_db.save_parse_log(log_data)
        assert result == True
        
        logs = test_db.get_parse_logs()
        assert len(logs) >= 1
        assert logs[0]['task_id'] == "task123"
    
    def test_get_parse_logs_limit(self, test_db):
        """测试限制返回数量"""
        for i in range(10):
            test_db.save_parse_log({
                "url": f"https://test.com/log{i}",
                "task_id": f"task{i}",
                "status": "success",
                "success": True
            })
        
        logs = test_db.get_parse_logs(limit=5)
        assert len(logs) <= 5


class TestCacheRules:
    """缓存规则测试"""
    
    def test_save_cache_rule(self, test_db):
        """测试保存缓存规则"""
        rule_data = {
            "rule_name": "youtube_high_quality",
            "rule_type": "quality_based",
            "platform": "youtube",
            "quality": "1080p",
            "ttl_seconds": 172800,
            "priority": 10,
            "is_active": True,
            "description": "YouTube 1080p视频缓存规则"
        }
        
        result = test_db.save_cache_rule(rule_data)
        assert result == True
        
        rules = test_db.get_cache_rules()
        assert len(rules) >= 1
        
        youtube_rule = next((r for r in rules if r['rule_name'] == 'youtube_high_quality'), None)
        assert youtube_rule is not None
        assert youtube_rule['ttl_seconds'] == 172800
    
    def test_delete_cache_rule(self, test_db):
        """测试删除缓存规则"""
        test_db.save_cache_rule({
            "rule_name": "to_delete",
            "rule_type": "default",
            "ttl_seconds": 86400
        })
        
        result = test_db.delete_cache_rule("to_delete")
        assert result == True
        
        rules = test_db.get_cache_rules()
        assert not any(r['rule_name'] == 'to_delete' for r in rules)


class TestVideoCacheManager:
    """缓存管理器测试"""
    
    def test_get_cache_ttl_default(self):
        """测试默认TTL"""
        if not DB_AVAILABLE:
            pytest.skip("数据库不可用")
        
        manager = VideoCacheManager()
        ttl = manager.get_cache_ttl("https://test.com/video", "unknown", "1080p", 180)
        assert ttl > 0
    
    def test_should_mark_as_hot(self):
        """测试热门标记判断"""
        if not DB_AVAILABLE:
            pytest.skip("数据库不可用")
        
        manager = VideoCacheManager()
        manager._hot_cache_threshold = 5
        
        result = manager.should_mark_as_hot("https://nonexistent.com/video", hit_count=10)
        assert result == False
    
    def test_validate_cache_not_exists(self):
        """测试验证不存在的缓存"""
        if not DB_AVAILABLE:
            pytest.skip("数据库不可用")
        
        manager = VideoCacheManager()
        result = manager.validate_cache("https://nonexistent.com/video")
        
        assert result['valid'] == False
        assert "不存在" in result['reason']


class TestCacheKeyGenerator:
    """缓存键生成器测试"""
    
    def test_compute_url_hash(self):
        """测试URL哈希计算"""
        generator = CacheKeyGenerator()
        hash1 = generator.compute_url_hash("https://test.com/video")
        hash2 = generator.compute_url_hash("https://test.com/video")
        hash3 = generator.compute_url_hash("https://test.com/other")
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64
    
    def test_normalize_url(self):
        """测试URL标准化"""
        generator = CacheKeyGenerator()
        
        url1 = "https://Test.com/Video?param=1"
        url2 = "https://test.com/Video?param=1"
        
        norm1 = generator.normalize_url(url1)
        norm2 = generator.normalize_url(url2)
        
        assert norm1 == norm2


class TestIntegration:
    """集成测试"""
    
    def test_full_cache_workflow(self, test_db):
        """测试完整缓存工作流"""
        if not DB_AVAILABLE:
            pytest.skip("数据库不可用")
        
        url = "https://integration.test.com/video"
        
        test_db.save_video({
            "url": url,
            "video_info": {
                "platform": "youtube",
                "video_id": "integration123",
                "title": "集成测试视频"
            },
            "metadata": {
                "duration": 300,
                "file_size": 209715200
            },
            "success": True
        })
        
        video = test_db.get_video(url)
        assert video is not None
        
        test_db.increment_hit_count(url)
        test_db.increment_hit_count(url)
        test_db.increment_hit_count(url)
        
        updated_video = test_db.get_video(url)
        assert updated_video['cache_hit_count'] == 3
        
        test_db.mark_as_hot(url)
        
        hot_video = test_db.get_video(url)
        assert hot_video['is_hot'] == 1
        
        test_db.save_parse_log({
            "url": url,
            "task_id": "integration_task",
            "status": "completed",
            "progress": 100,
            "success": True,
            "duration_ms": 2500
        })
        
        logs = test_db.get_parse_logs()
        integration_logs = [l for l in logs if l['task_id'] == 'integration_task']
        assert len(integration_logs) >= 1
        
        stats = test_db.get_stats()
        assert stats['total_videos'] >= 1
    
    def test_cache_expiration_workflow(self, test_db):
        """测试缓存过期工作流"""
        if not DB_AVAILABLE:
            pytest.skip("数据库不可用")
        
        test_db.save_video({
            "url": "https://expire.test.com/video",
            "video_info": {},
            "metadata": {},
            "success": True
        })
        
        test_db.update_cache_status("https://expire.test.com/video", "expired")
        
        video = test_db.get_video("https://expire.test.com/video")
        assert video['cache_status'] == "expired"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
