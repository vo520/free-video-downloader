import os
import asyncio
import ipaddress
import socket
import time
import warnings
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from urllib.parse import unquote, urlparse, urljoin

from dotenv import load_dotenv
load_dotenv()

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, field_validator

DEFAULT_FORMAT_ID = "bestvideo+bestaudio/best"

from downloader import VideoDownloader
from douyin import DouyinParser, is_douyin_url
from database import init_db, add_history
from auth import get_optional_user


downloader = VideoDownloader()
douyin_parser = DouyinParser(download_dir=downloader.DOWNLOAD_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    download_dir = downloader.DOWNLOAD_DIR
    if os.path.exists(download_dir):
        for f in os.listdir(download_dir):
            try:
                os.remove(os.path.join(download_dir, f))
            except OSError:
                pass


app = FastAPI(
    title="万能视频下载器 API",
    description="基于 yt-dlp 的万能视频下载服务，支持 1800+ 平台",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS：避免使用 allow_origins=["*"] 的同时开启 allow_credentials（浏览器会拒绝该非法组合）。
# 通过 CORS_ORIGINS 环境变量配置可信前端源（逗号分隔）；默认开发环境 localhost 源。
# 仅当 origins 不包含通配符 "*" 时才允许携带凭证，避免凭据泄露到任意域。
_raw_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
)
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
_allow_credentials = "*" not in _allowed_origins

# 带凭证时不能用通配符方法与头（浏览器会拒绝凭据请求），故始终使用显式列表，
# 兼顾"无凭证 + 通配源"与"有凭证 + 限定源"两种场景的合法性。
_CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"]
_CORS_HEADERS = ["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=_CORS_METHODS,
    allow_headers=_CORS_HEADERS,
)


# ---------- 客户端 IP 提取 ----------
def _client_ip(request: "Request") -> str:
    """提取客户端真实 IP；若显式配置 TRUST_PROXY 则优先读取 X-Forwarded-For。"""
    if os.getenv("TRUST_PROXY"):
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------- 轻量内存滑动窗口限流 ----------
class RateLimiter:
    """按 key（此处为客户端 IP）的滑动窗口限流，仅使用标准库，无需额外依赖。"""

    def __init__(self, max_requests: int, window_seconds: int, max_keys: int = 2000):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._hits: "dict[str, deque]" = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        dq = self._hits[key]
        while dq and dq[0] <= now - self.window_seconds:
            dq.popleft()
        # 修复内存泄漏：过期窗口清空后及时删除空 deque，避免空条目长期驻留
        if not dq:
            self._hits.pop(key, None)
        if key in self._hits and len(self._hits[key]) >= self.max_requests:
            return False
        self._hits[key].append(now)
        # 控制内存：键过多时先清理空窗口；若仍超限（大量不同 IP 的分布式请求），
        # 淘汰全局最旧的一条记录，保证字典有界、避免被请求打爆内存。
        if len(self._hits) > self.max_keys:
            for k in [k for k, v in self._hits.items() if not v]:
                self._hits.pop(k, None)
            if len(self._hits) > self.max_keys:
                oldest = min(self._hits, key=lambda k: self._hits[k][0])
                self._hits.pop(oldest, None)
        return True

    def retry_after(self, key: str) -> float:
        dq = self._hits.get(key)
        if not dq:
            return 0.0
        return max(0.0, (dq[0] + self.window_seconds) - time.monotonic())


# 下载为重操作（落盘 + 占线程），更严格；解析/直链较轻。
_download_limiter = RateLimiter(max_requests=5, window_seconds=60)
_parse_limiter = RateLimiter(max_requests=20, window_seconds=60)
_direct_limiter = RateLimiter(max_requests=20, window_seconds=60)


def _limit(request: "Request", limiter: RateLimiter) -> None:
    ip = _client_ip(request)
    if not limiter.is_allowed(ip):
        retry = int(limiter.retry_after(ip)) + 1
        raise HTTPException(
            status_code=429,
            detail={"success": False, "error": "请求过于频繁，请稍后再试"},
            headers={"Retry-After": str(retry)},
        )


def _dep_limit_download(request: "Request") -> None:
    _limit(request, _download_limiter)


def _dep_limit_parse(request: "Request") -> None:
    _limit(request, _parse_limiter)


def _dep_limit_direct(request: "Request") -> None:
    _limit(request, _direct_limiter)


# ---------- 缩略图代理 SSRF 防护 ----------
# 仅允许 http/https；解析主机对应所有 IP，任一命中保留/私有网段即拒绝（缓解 DNS 重绑定）。
_BLOCKED_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8", "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
        "::1/128", "fc00::/7", "fe80::/10", "64:ff9b::/96",
    )
]


# 缩略图代理不自动跟随重定向：每一跳都须重新过 SSRF 校验，最多跟 5 跳，
# 否则公开 URL → 内网/云元数据的 302 跳转即可绕过防护。
_MAX_REDIRECT_HOPS = 5
_REDIRECT_STATUS = (301, 302, 303, 307, 308)


def _is_safe_thumbnail_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip_obj = ipaddress.ip_address(addr)
        except ValueError:
            return False
        # 仅允许公网地址；任何非全局（回环/私有/链路本地/保留/多播/未指定等）一律拒绝
        if not ip_obj.is_global:
            return False
        if any(ip_obj in net for net in _BLOCKED_NETS):
            return False
    return True


class ParseRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str = DEFAULT_FORMAT_ID
    title: str = ""
    platform: str = ""

    @field_validator("format_id")
    @classmethod
    def _normalize_format_id(cls, v: str) -> str:
        # 前端可能传空字符串（如解析成功但无可用格式时预览/下载），
        # Pydantic 默认值对空串不生效，此处统一归一为最佳格式，
        # 避免空 format 直达 yt-dlp 导致 400。
        return (v or "").strip() or DEFAULT_FORMAT_ID


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "万能视频下载器服务运行中"}


@app.post("/api/parse", dependencies=[Depends(_dep_limit_parse)])
async def parse_video(req: ParseRequest, user: dict | None = Depends(get_optional_user)):
    """解析视频信息（抖音走专用模块，其他走 yt-dlp）"""
    try:
        loop = asyncio.get_running_loop()
        url = req.url.strip()
        # 处理裸数字抖音 ID（抖音视频 ID 为纯数字）。注意：勿对"任意 >10 位字母数字串"
        # 做转换——否则会把 YouTube 等平台的 11 位视频 ID（如 dQw4w9WgXcQ）误判为抖音，
        # 从而转成错误链接导致解析失败。
        if url.isdigit():
            url = f"https://www.douyin.com/video/{url}"
        # SSRF/本地文件读取防护：匿名入口必须拦掉 file:// 与内网地址。
        url = _validate_public_url(url)
        if is_douyin_url(url):
            # 抖音私有接口可能长时间阻塞（如 WAF 暴力求解），加超时降级避免占满线程
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, douyin_parser.parse, url),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail={
                    "success": False, "error": "抖音解析超时，请稍后重试"
                })
        else:
            # yt-dlp 解析个别站点可能长时间挂起，加超时避免线程被永久占满
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, downloader.parse_video, url),
                    timeout=120,
                )
            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail={
                    "success": False, "error": "解析超时，请稍后重试"
                })
        # 已登录用户记录解析历史（best-effort；add_history 内部已吞异常并 warning，失败不影响主返回）。
        # snapshot=result 存完整 videoData（含 formats/duration/uploader 等），使历史回看不必重跑 yt-dlp。
        if user:
            add_history(
                user["id"], "parse",
                video_url=url,
                title=result.get("title"),
                platform=result.get("platform"),
                thumbnail=result.get("thumbnail"),
                snapshot=result,
            )
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "success": False,
            "error": f"解析失败: {str(e)}"
        })


@app.post("/api/download", dependencies=[Depends(_dep_limit_download)])
async def download_video(req: DownloadRequest, user: dict | None = Depends(get_optional_user)):
    """服务端下载视频后提供文件下载（抖音走专用模块）"""
    try:
        loop = asyncio.get_running_loop()
        url = req.url.strip()
        # 处理裸数字抖音 ID（抖音视频 ID 为纯数字）。注意：勿对"任意 >10 位字母数字串"
        # 做转换——否则会把 YouTube 等平台的 11 位视频 ID（如 dQw4w9WgXcQ）误判为抖音，
        # 从而转成错误链接导致解析失败。
        if url.isdigit():
            url = f"https://www.douyin.com/video/{url}"
        # SSRF/本地文件读取防护：匿名入口必须拦掉 file:// 与内网地址。
        url = _validate_public_url(url)
        if is_douyin_url(url):
            # 抖音下载同样可能阻塞，加超时降级。根据 format_id 选择视频/仅音频模式
            # （复用既有 DouyinParser.download，不新增接口）
            douyin_mode = "audio" if "audio" in req.format_id else "video"
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, douyin_parser.download, url, douyin_mode),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail={
                    "success": False, "error": "抖音下载超时，请稍后重试"
                })
        else:
            # yt-dlp 下载大文件可能耗时很久，加宽松超时（30 分钟）避免线程被永久占满
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, downloader.download_video, url, req.format_id
                    ),
                    timeout=1800,
                )
            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail={
                    "success": False, "error": "下载超时，请稍后重试或更换清晰度"
                })
        filepath = result["filepath"]
        if not os.path.exists(filepath):
            raise HTTPException(status_code=500, detail="下载的文件不存在")

        # 已登录用户记录下载历史（best-effort；add_history 内部已吞异常并 warning，失败不影响主返回）
        if user:
            add_history(
                user["id"], "download",
                video_url=url,
                title=req.title or None,
                platform=req.platform or None,
                extra={"format_id": req.format_id},
            )
        return FileResponse(
            path=filepath,
            filename=result["filename"],
            media_type="application/octet-stream",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "success": False,
            "error": f"下载失败: {str(e)}"
        })


@app.post("/api/direct-url", dependencies=[Depends(_dep_limit_direct)])
async def get_direct_url(req: DownloadRequest):
    """获取视频直链"""
    try:
        loop = asyncio.get_running_loop()
        url = req.url.strip()
        # 与解析/下载一致：裸数字抖音 ID 转为完整链接，否则会被 URL 校验直接拒绝
        if url.isdigit():
            url = f"https://www.douyin.com/video/{url}"
        # SSRF/本地文件读取防护：与解析/下载一致的匿名入口校验。
        url = _validate_public_url(url)
        # 与解析同级的超时（120s）：避免 yt-dlp 在 executor 线程中无限挂起占满线程
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None, downloader.get_direct_url, url, req.format_id
            ),
            timeout=120,
        )
        return {"success": True, "data": result}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail={
            "success": False, "error": "获取直链超时，请稍后重试"
        })
    except HTTPException:
        # URL 校验抛出的 400 原样透传，避免被下方通用分支二次包装成字符串化 detail
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "success": False,
            "error": f"获取直链失败: {str(e)}"
        })


def _resolve_safe_ip(url: str):
    """解析并校验 URL 主机为公网地址，返回 (ip, parsed_url)。失败返回 (None, None)。

    在发送请求前固定解析一次 IP，后续用 IP 直连 + Host 头，避免 httpx 再次解析
    造成的 DNS 重绑定（TOCTOU）绕过 SSRF 校验。
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        return None, None
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return None, None
    for info in infos:
        addr = info[4][0]
        try:
            ip_obj = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip_obj.is_global and not any(ip_obj in net for net in _BLOCKED_NETS):
            return addr, parsed
    return None, None


def _validate_public_url(raw_url: str) -> str:
    """校验用户输入的解析/下载/直链 URL：仅允许公网 http/https，拒绝指向内网/环回/
    链路本地/保留/多播地址（防 SSRF 与 file:// 等本地文件读取）。
    返回规范化后的 URL；不合法抛 400。用标准库地址分类而非 is_global，避免误伤正常
    公网 CDN（如 100.64.0.0/10 共享地址）。"""
    url = (raw_url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "仅支持公网 http/https 视频链接"},
        )
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except (socket.gaierror, UnicodeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "无法解析视频链接主机"},
        )
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        # IPv4-mapped IPv6（::ffff:127.0.0.1）按其内嵌 IPv4 判定，避免绕过
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if (
            ip.is_private
            or ip.is_unspecified
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": "不支持的链接地址"},
            )
    return url


@app.get("/api/proxy/thumbnail")
async def proxy_thumbnail(url: str = Query(..., description="缩略图URL")):
    """代理获取视频缩略图，绕过防盗链（带 SSRF 防护，且对重定向链路逐跳校验）"""
    MAX_THUMBNAIL_BYTES = 10 * 1024 * 1024
    # 不自动跟随重定向：每次跳转都要重新过 SSRF 校验，避免"公开 URL → 内网/云元数据"的跳转绕过。
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            current = url
            for _ in range(_MAX_REDIRECT_HOPS):
                # 每一跳（含起点）都校验目标地址为公网，杜绝 DNS 重绑定/重定向绕过
                if not _is_safe_thumbnail_url(current):
                    raise HTTPException(status_code=400, detail="不支持的缩略图地址")
                ip, parsed = _resolve_safe_ip(current)
                if not ip:
                    raise HTTPException(status_code=400, detail="不支持的缩略图地址")
                # 用已校验的固定 IP 直连，Host 头保留原主机名，避免请求时再次解析 DNS 造成重绑定
                target = f"{parsed.scheme}://{ip}{parsed.path or '/'}"
                if parsed.query:
                    target += "?" + parsed.query
                resp = await client.get(
                    target,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": current,
                        "Host": parsed.hostname,
                    },
                )
                if resp.status_code in _REDIRECT_STATUS and resp.headers.get("location"):
                    current = urljoin(current, resp.headers["location"])
                    continue
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                # 缺省不臆测为图片：必须显式声明的 image/* 才放行，避免代理回显任意内容（如内网 HTML/JSON）。
                if not content_type.startswith("image/"):
                    raise HTTPException(status_code=400, detail="缩略图格式不支持")
                # 流式累加并限制最大体积，防止内存耗尽。
                content = b""
                async for chunk in resp.aiter_bytes(8192):
                    content += chunk
                    if len(content) > MAX_THUMBNAIL_BYTES:
                        raise HTTPException(status_code=413, detail="缩略图体积过大")
                return StreamingResponse(
                    iter([content]),
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
            # 循环正常结束说明重定向次数超限
            raise HTTPException(status_code=400, detail="缩略图重定向链路过长")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="缩略图加载失败")


# 挂载功能模块路由
from api_summarize import router as summarize_router
from api_auth import router as auth_router
from api_payment import router as payment_router
from api_video_cache import router as video_cache_router
from api_history import router as history_router

app.include_router(summarize_router)
app.include_router(auth_router)
app.include_router(payment_router)
app.include_router(video_cache_router)
app.include_router(history_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
