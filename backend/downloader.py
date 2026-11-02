import os
import re
import shutil
import threading
import yt_dlp
from typing import Optional


# 下载临时目录磁盘配额：超过该值时按修改时间清理旧文件（先清理已完成文件，.part 最后）。
MAX_DOWNLOAD_DIR_BYTES = 2 * 1024 * 1024 * 1024  # 2GB

# 清理操作为进程内全局串行：避免并发下载请求同时执行清理，
# 误删彼此正在写入的 .part 文件导致下载失败。
_quota_lock = threading.Lock()


def _enforce_quota(download_dir: str, limit: int = MAX_DOWNLOAD_DIR_BYTES) -> None:
    """下载目录超过配额时，按修改时间从旧到新删除文件直至低于阈值。

    .part 是下载中的临时文件（yt-dlp / douyin 都写 xxx.mp4.part），
    必须最后才清理：先前的排序让 .part 排在最前、优先被删，一次配额清理就会
    打断另一个并发请求正在进行的下载。现在先删已完成文件（旧的优先），
    只有当目录里只剩 .part 时才动它们。
    使用进程锁保证并发下载时清理串行执行。
    用于防止服务端落盘无上限导致磁盘写满。
    """
    with _quota_lock:
        try:
            entries = [
                os.path.join(download_dir, f)
                for f in os.listdir(download_dir)
                if os.path.isfile(os.path.join(download_dir, f))
            ]
        except OSError:
            return
        if not entries:
            return
        # 逐个取 size/mtime：并发下载会在 listdir 之后把 .part rename 成正式文件
        # （douyin / yt-dlp 都这么做）或删除文件，getsize/getmtime 抛 FileNotFoundError。
        # 原实现直接 sum(getsize) + sort(getmtime)，一旦命中就让整个下载请求失败；
        # 配额清理是 best-effort，跳过已消失的文件即可。
        total = 0
        sized = []
        for e in entries:
            try:
                size = os.path.getsize(e)
                mtime = os.path.getmtime(e)
            except OSError:
                continue
            total += size
            sized.append((e, size, mtime))
        if total <= limit:
            return
        # 排序键：(是否为 .part, mtime) —— 已完成文件优先删、更旧的优先；
        # .part 排最后，避免配额清理打断正在进行的并发下载。
        sized.sort(key=lambda item: (1 if item[0].endswith(".part") else 0, item[2]))
        for e, size, _mtime in sized:
            if total <= limit:
                break
            try:
                os.remove(e)
            except OSError:
                # 删除失败（已被并发删除/占用）时不扣减 size，继续尝试下一个
                continue
            total -= size


def _find_ffmpeg_path() -> Optional[str]:
    """查找 ffmpeg 可执行文件路径"""
    if shutil.which("ffmpeg"):
        return os.path.dirname(shutil.which("ffmpeg"))
    try:
        import static_ffmpeg
        paths = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
        return os.path.dirname(paths[0])
    except Exception:
        return None


class VideoDownloader:
    """yt-dlp 封装层，提供视频解析、下载、直链获取能力"""

    DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")

    def __init__(self):
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
        self.ffmpeg_path = _find_ffmpeg_path()
        self.has_ffmpeg = self.ffmpeg_path is not None

    def ensure_disk_quota(self) -> None:
        """下载前调用：确保临时目录不超出磁盘配额。"""
        _enforce_quota(self.DOWNLOAD_DIR)

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "_", name)

    @staticmethod
    def _format_filesize(size: Optional[int]) -> str:
        if not size:
            return "未知大小"
        if size < 1024 * 1024:
            return f"{size / 1024:.0f}KB"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        return f"{size / (1024 * 1024 * 1024):.2f}GB"

    @staticmethod
    def _format_duration(seconds: Optional[int]) -> str:
        if not seconds:
            return "00:00"
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def parse_video(self, url: str) -> dict:
        """解析视频信息，不下载文件"""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,
            "extractor_retries": 3,
            "fragment_retries": 3,
            "skip_unavailable_fragments": False,
            "ignoreerrors": False,
        }
        
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ydl_opts["http_headers"] = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise ValueError("无法解析该链接")

        formats = self._extract_formats(info)
        platform = info.get("extractor", info.get("extractor_key", "Unknown"))

        return {
            "id": info.get("id", ""),
            "title": info.get("title", "未知标题"),
            "thumbnail": info.get("thumbnail", ""),
            "duration": info.get("duration"),
            "duration_string": self._format_duration(info.get("duration")),
            "uploader": info.get("uploader", info.get("channel", "未知")),
            "platform": platform,
            "view_count": info.get("view_count"),
            "upload_date": info.get("upload_date", ""),
            "description": (info.get("description") or "")[:200],
            "formats": formats,
            "subtitles": list(info.get("subtitles", {}).keys()),
            "automatic_captions": list(info.get("automatic_captions", {}).keys())[:5],
        }

    def _extract_formats(self, info: dict) -> list:
        """从 yt-dlp info 中提取并整理可用格式"""
        raw_formats = info.get("formats", [])
        if not raw_formats:
            return []

        seen = set()
        results = []

        # 先收集有音频的格式
        av_formats = []
        v_only_formats = []
        best_height = 0

        for f in raw_formats:
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            height = f.get("height") or 0
            ext = f.get("ext", "mp4")
            format_id = f.get("format_id", "")

            has_video = vcodec and vcodec != "none"
            has_audio = acodec and acodec != "none"

            if not has_video:
                continue

            if height > best_height:
                best_height = height

            resolution = f"{f.get('width', '?')}x{height}" if height else "未知"
            filesize = f.get("filesize") or f.get("filesize_approx")
            size_label = self._format_filesize(filesize)

            if has_audio:
                label = f"{height}p {ext.upper()} ({size_label})"
                av_formats.append({
                    "format_id": format_id,
                    "ext": ext,
                    "resolution": resolution,
                    "height": height,
                    "filesize": filesize,
                    "filesize_approx": filesize,
                    "vcodec": vcodec,
                    "acodec": acodec,
                    "has_audio": True,
                    "label": label,
                })
            else:
                label = f"{height}p {ext.upper()} (仅视频, {size_label})"
                v_only_formats.append({
                    "format_id": format_id,
                    "ext": ext,
                    "resolution": resolution,
                    "height": height,
                    "filesize": filesize,
                    "filesize_approx": filesize,
                    "vcodec": vcodec,
                    "acodec": None,
                    "has_audio": False,
                    "label": label,
                })

        # 按 height 去重并排序
        av_dict = {}
        for fmt in av_formats:
            key = (fmt["height"], fmt["ext"])
            if key not in av_dict:
                av_dict[key] = fmt

        v_dict = {}
        for fmt in v_only_formats:
            key = (fmt["height"], fmt["ext"])
            if key not in v_dict:
                v_dict[key] = fmt

        # 优先添加有音频的格式
        for key in sorted(av_dict.keys(), key=lambda x: x[0], reverse=True):
            results.append(av_dict[key])
            seen.add(key)

        # 添加合并格式选项（如果没有足够的有音频格式）
        if v_dict and not av_dict:
            # 所有格式都是纯视频，需要合并
            best_video = max(v_dict.values(), key=lambda x: x["height"])
            results.insert(0, {
                "format_id": "bestvideo+bestaudio/best",
                "ext": "mp4",
                "resolution": best_video["resolution"],
                "height": best_video["height"],
                "filesize": None,
                "filesize_approx": None,
                "vcodec": "merged",
                "acodec": "merged",
                "has_audio": True,
                "label": f"最佳画质 {best_video['height']}p (自动合并音频)",
            })
        elif av_dict:
            # 已有有音频格式，但添加一个合并选项作为备选
            best_av = max(av_dict.values(), key=lambda x: x["height"])
            if not any("+" in f["format_id"] for f in results):
                results.insert(0, {
                    "format_id": "bestvideo+bestaudio/best",
                    "ext": "mp4",
                    "resolution": best_av["resolution"],
                    "height": best_av["height"],
                    "filesize": None,
                    "filesize_approx": None,
                    "vcodec": "merged",
                    "acodec": "merged",
                    "has_audio": True,
                    "label": f"最佳画质 {best_av['height']}p (自动合并音频)",
                })

        # 提供"仅音频"选项，使前端的"仅音频"预设真正可用（yt-dlp 支持 bestaudio 选择器）
        results.append({
            "format_id": "bestaudio",
            "ext": "m4a",
            "resolution": "音频",
            "height": 0,
            "filesize": None,
            "filesize_approx": None,
            "vcodec": "none",
            "acodec": "merged",
            "has_audio": True,
            "label": "仅音频 M4A (自动提取)",
        })

        results.sort(key=lambda x: x["height"], reverse=True)

        # 钉住"最佳画质（自动合并）"与"仅音频"两个预设项，确保即便格式很多被截断，
        # 前端的"仅音频"预设也始终可用（避免 results[:15] 把 height=0 的音频项裁掉）。
        _PINNED = ("bestvideo+bestaudio/best", "bestaudio")
        pinned = [f for f in results if f["format_id"] in _PINNED]
        rest = [f for f in results if f["format_id"] not in _PINNED]
        return (pinned + rest)[:15]

    def download_video(self, url: str, format_id: str) -> dict:
        """下载视频到服务器临时目录，返回文件路径和元数据"""
        if not self.has_ffmpeg and "+" in format_id:
            format_id = "best"

        # 下载前确保临时目录不超出磁盘配额（防止写满磁盘）
        self.ensure_disk_quota()

        ydl_opts = {
            "format": format_id,
            # 文件名含视频 id，避免不同视频同标题时相互覆盖
            "outtmpl": os.path.join(self.DOWNLOAD_DIR, "%(title)s [%(id)s].%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ydl_opts["http_headers"] = {
            "User-Agent": user_agent,
        }

        if self.has_ffmpeg:
            ydl_opts["ffmpeg_location"] = self.ffmpeg_path
            ydl_opts["merge_output_format"] = "mp4"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        if not info:
            raise ValueError("下载失败")

        # 以 yt-dlp 实际落盘名为准（outtmpl 含视频 id，且与 extensions/合并后真实文件名一致），
        # 避免用"已 sanitize 的 title.ext"去拼路径导致 os.path.exists 恒为 False、回退逻辑误命中。
        prepared = ydl.prepare_filename(info)
        if os.path.exists(prepared):
            filepath = prepared
        else:
            # 兜底：极少数情况下合并输出名与 prepare_filename 不一致，按视频 id 在目录内定位
            _vid = info.get("id")
            _candidates = [
                os.path.join(self.DOWNLOAD_DIR, f)
                for f in os.listdir(self.DOWNLOAD_DIR)
                if os.path.isfile(os.path.join(self.DOWNLOAD_DIR, f))
                and _vid
                and _vid in f
            ]
            if _candidates:
                filepath = _candidates[0]
            else:
                raise FileNotFoundError("下载完成但未找到落盘文件")

        return {
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "title": info.get("title", "video"),
            "ext": info.get("ext", "mp4"),
        }

    def get_direct_url(self, url: str, format_id: str) -> dict:
        """获取视频直链"""
        ydl_opts = {
            "format": format_id,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ydl_opts["http_headers"] = {
            "User-Agent": user_agent,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise ValueError("无法获取直链")

        direct_url = info.get("url")
        ext = info.get("ext") or "mp4"
        filesize = info.get("filesize") or info.get("filesize_approx")

        if not direct_url and "+" in format_id:
            # 合并选择器（前端默认的 bestvideo+bestaudio/best）不会产出单一的 info["url"]，
            # requested_formats 里分别是纯视频流与纯音频流。直接取 requested_formats[0]
            # 拿到的是无音轨视频 → 前端内联预览有画面没声音。
            # 因此优先在 info["formats"] 中挑一个同时含视频+音频的渐进式格式；找不到再退回原行为。
            progressive = self._pick_progressive_format(info.get("formats") or [])
            if progressive:
                direct_url = progressive.get("url")
                ext = progressive.get("ext") or ext
                filesize = (
                    progressive.get("filesize")
                    or progressive.get("filesize_approx")
                    or filesize
                )

        if not direct_url:
            requested = info.get("requested_formats")
            if requested and len(requested) > 0:
                direct_url = requested[0].get("url")

        if not direct_url:
            raise ValueError("该视频不支持直链下载，请使用服务端下载模式")

        return {
            "direct_url": direct_url,
            "ext": ext,
            "filesize": filesize,
            "title": info.get("title", "video"),
        }

    @staticmethod
    def _pick_progressive_format(formats: list) -> Optional[dict]:
        """挑选同时含视频与音频、且带直链的渐进式格式。

        合并选择器下 requested_formats 是拆开的视频流/音频流，无法单独播放出声音；
        只有渐进式格式（vcodec 与 acodec 都不是 none）能直接用于浏览器内联预览。
        优先分辨率最高，同分辨率优先 mp4。
        """
        candidates = []
        for f in formats or []:
            if not f.get("url"):
                continue
            vcodec = f.get("vcodec") or "none"
            acodec = f.get("acodec") or "none"
            if vcodec == "none" or acodec == "none":
                continue
            candidates.append(f)
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda f: (f.get("height") or 0, 1 if f.get("ext") == "mp4" else 0),
        )
