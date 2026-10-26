"""AI 视频总结相关 API 路由（独立模块，通过 include_router 挂载）"""

import asyncio
import json
from collections.abc import AsyncIterable

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from auth import get_optional_user
from database import check_and_increment_summary, check_summary_quota, FREE_DAILY_SUMMARY_LIMIT, add_history

router = APIRouter(prefix="/api", tags=["AI 总结"])


class SummarizeRequest(BaseModel):
    url: str
    language: str = "zh"
    # 供历史落地记录标题/平台（向后兼容：旧前端不传则留空）。
    title: str = ""
    platform: str = ""


class ChatRequest(BaseModel):
    url: str
    question: str
    subtitle_text: str = ""


def _check_summary_permission(user: dict | None):
    """
    检查 AI 总结权限。
    未登录用户：不允许使用。
    免费用户：每日限制次数。
    VIP 用户：无限制。
    返回 (allowed, remaining, message)
    """
    if not user:
        return False, 0, "请先登录后使用 AI 总结功能"

    allowed, remaining = check_summary_quota(user["id"])
    if not allowed:
        return False, 0, f"今日免费 AI 总结次数已用完（每日 {FREE_DAILY_SUMMARY_LIMIT} 次），开通 VIP 可无限使用"

    return True, remaining, None


def _get_summarizer():
    """延迟初始化 VideoSummarizer（仅在首次调用时创建）"""
    from summarizer import VideoSummarizer
    if not hasattr(_get_summarizer, "_instance"):
        try:
            _get_summarizer._instance = VideoSummarizer()
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
    return _get_summarizer._instance


def _get_extractor():
    """延迟初始化 SubtitleExtractor"""
    from summarizer import SubtitleExtractor
    if not hasattr(_get_extractor, "_instance"):
        _get_extractor._instance = SubtitleExtractor()
    return _get_extractor._instance


def _validate_video_url(raw_url: str) -> str | None:
    """校验 AI 总结/问答传入的视频 URL。

    字幕提取会把 url 交给 yt-dlp / httpx 发起服务端请求，因此与 /api/parse、
    /api/download、/api/direct-url 一样必须拦掉 file:// 与内网地址，否则任何登录
    用户都能借本接口探测内网服务与云元数据（SSRF）。返回 None 表示合法，否则返回
    可直接回给前端的错误文案。延迟 import main 以避免与 main 的 include_router 循环导入。
    """
    from main import _validate_public_url

    try:
        _validate_public_url(raw_url)
        return None
    except HTTPException as e:
        detail = e.detail
        msg = detail.get("error") if isinstance(detail, dict) else str(detail)
        # 主机解析失败时不拦截：解析不出地址就不存在可被 SSRF 命中的目标，真实抓取时
        # yt-dlp 会自然失败；同时避免离线环境（CI/单测）因 DNS 不可用被误判为非法链接。
        if msg == "无法解析视频链接主机":
            return None
        return msg or "不支持的视频链接"


_STREAM_END = object()


async def _iterate_in_executor(gen):
    """在线程池中逐个拉取同步生成器的元素。

    summarize_stream / chat_stream 是同步生成器，每次 next() 都会阻塞等待 LLM 网络 IO；
    直接在 async 函数里 for 迭代会卡住整个事件循环（期间所有请求无响应）。
    """
    loop = asyncio.get_running_loop()
    it = iter(gen)
    try:
        while True:
            item = await loop.run_in_executor(None, next, it, _STREAM_END)
            if item is _STREAM_END:
                return
            yield item
    finally:
        close = getattr(it, "close", None)
        if close:
            try:
                close()
            except ValueError:
                # 任务被取消时线程可能仍在执行 next()，此时无法 close，交由 GC 回收
                pass


async def _summarize_stream(req: SummarizeRequest, user: dict | None, request: Request):
    """生成 SSE 事件流"""
    allowed, remaining, message = _check_summary_permission(user)
    if not allowed:
        yield ServerSentEvent(
            data=json.dumps({"message": message, "need_login": user is None, "need_vip": user is not None}, ensure_ascii=False),
            event="error",
        )
        return

    # SSRF 防护：拒绝 file:// 与内网地址后再进入字幕提取/LLM 调用。
    url_error = _validate_video_url(req.url)
    if url_error:
        yield ServerSentEvent(
            data=json.dumps({"message": url_error}, ensure_ascii=False),
            event="error",
        )
        return

    try:
        loop = asyncio.get_running_loop()
        extractor = _get_extractor()
        # 加超时：避免 yt-dlp 在个别站点卡死时永久占满 executor 线程导致整体夯死。
        subtitle_data = await asyncio.wait_for(
            loop.run_in_executor(None, extractor.extract, req.url),
            timeout=120,
        )

        yield ServerSentEvent(
            data=json.dumps(subtitle_data, ensure_ascii=False),
            event="subtitle",
        )

        if not subtitle_data["has_subtitle"]:
            yield ServerSentEvent(
                data=json.dumps({"message": "该视频没有可用的字幕，无法生成总结"}, ensure_ascii=False),
                event="error",
            )
            return

        # 确认有字幕、将真正生成总结，此时才消费一次免费额度，
        # 避免无字幕/提取失败等场景白白扣减用户免费次数。
        _, remaining = check_and_increment_summary(user["id"])

        full_text = subtitle_data["full_text"]
        summarizer = _get_summarizer()

        # 收集总结全文，供历史回看（token 为纯文本字符串，直接拼接）。
        summary_text = ""
        async for token in _iterate_in_executor(summarizer.summarize_stream(full_text, req.language)):
            # 客户端中途关闭/路由切走：直接停止 yield，不再继续调用 mindmap 与 add_history，
            # 避免 LLM API 配额与算力被白白消耗；check_and_increment_summary 已消耗的不退，
            # 避免引入新的"配额回滚"一致性复杂度（无字幕/失败扣减的设计思路一致）。
            if await request.is_disconnected():
                return
            yield ServerSentEvent(data=json.dumps(token, ensure_ascii=False), event="summary")
            summary_text += token

        # mindmap 是另一次昂贵的 LLM 调用，再检测一次避免短流后客户端已断仍白做。
        if await request.is_disconnected():
            return
        mindmap_md = await loop.run_in_executor(
            None, summarizer.generate_mindmap, full_text, req.language
        )
        # mindmap 调完客户端可能也已断开，最后再检一次，避免无意义的事件发送与落库。
        if await request.is_disconnected():
            return
        yield ServerSentEvent(
            data=json.dumps({"markdown": mindmap_md}, ensure_ascii=False),
            event="mindmap",
        )

        quota_info = {"remaining": remaining, "limit": FREE_DAILY_SUMMARY_LIMIT}
        yield ServerSentEvent(
            data=json.dumps(quota_info, ensure_ascii=False),
            event="quota",
        )

        yield ServerSentEvent(data="[DONE]", event="done")

        # best-effort：已登录用户记录总结历史，存全文供回看；失败不影响 SSE 主流程。
        # add_history 内部已吞异常并 warning，此处无需再包 try/except。
        if user:
            add_history(
                user["id"], "summary",
                video_url=req.url,
                title=req.title or None,
                platform=req.platform or None,
                extra={"summary": summary_text, "mindmap": mindmap_md},
            )

    except asyncio.TimeoutError:
        # TimeoutError 的 str() 为空，单独给出明确提示
        yield ServerSentEvent(
            data=json.dumps({"message": "总结失败: 字幕提取超时，请稍后重试"}, ensure_ascii=False),
            event="error",
        )
    except Exception as e:
        yield ServerSentEvent(
            data=json.dumps({"message": f"总结失败: {str(e)}"}, ensure_ascii=False),
            event="error",
        )


@router.post("/summarize")
async def summarize_video(
    req: SummarizeRequest,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """
    AI 视频总结（SSE 流式）
    事件类型: subtitle / summary / mindmap / done / error / quota
    """
    return EventSourceResponse(_summarize_stream(req, user, request))


async def _chat_stream(req: ChatRequest, user: dict | None, request: Request):
    """生成聊天响应流"""
    # C3：与 /api/summarize 一致，要求登录后再使用 AI 问答，避免匿名绕过。
    if not user:
        yield ServerSentEvent(
            data=json.dumps(
                {"message": "请先登录后使用 AI 问答功能", "need_login": True},
                ensure_ascii=False,
            ),
            event="error",
        )
        return

    # 与 /api/summarize 一致：免费用户受每日配额限制，VIP 无限。
    # 先做权限闸门（只校验、不消耗），避免后续字幕提取已完成却因配额不足白做。
    allowed, _, perm_message = _check_summary_permission(user)
    if not allowed:
        yield ServerSentEvent(
            data=json.dumps(
                {"message": perm_message, "need_login": False, "need_vip": True},
                ensure_ascii=False,
            ),
            event="error",
        )
        return

    # 问题为空则无需发起 AI 调用，直接提示，避免浪费配额/算力（前端已拦，后端再兜底）。
    if not req.question or not req.question.strip():
        yield ServerSentEvent(
            data=json.dumps({"message": "请输入问题后再发送", "need_login": False}, ensure_ascii=False),
            event="error",
        )
        return

    try:
        if not req.subtitle_text.strip():
            # 仅在实际需要抓取字幕时才校验 URL（前端已传字幕时不发起任何服务端请求）。
            url_error = _validate_video_url(req.url)
            if url_error:
                yield ServerSentEvent(
                    data=json.dumps({"message": url_error}, ensure_ascii=False),
                    event="error",
                )
                return
            loop = asyncio.get_running_loop()
            extractor = _get_extractor()
            # 加超时：与 summarize 一致，防止字幕提取卡死线程。
            subtitle_data = await asyncio.wait_for(
                loop.run_in_executor(None, extractor.extract, req.url),
                timeout=120,
            )
            if not subtitle_data["has_subtitle"]:
                yield ServerSentEvent(
                    data=json.dumps({"message": "该视频没有可用的字幕，无法回答问题"}, ensure_ascii=False),
                    event="error",
                )
                return
            subtitle_text = subtitle_data["full_text"]
        else:
            subtitle_text = req.subtitle_text

        # 确认有字幕、将真正发起问答，此时才消费一次免费额度
        # （与 summarize 一致：先校验字幕有效性，避免提取失败等场景白白扣减）。
        _, remaining = check_and_increment_summary(user["id"])

        summarizer = _get_summarizer()
        async for token in _iterate_in_executor(summarizer.chat_stream(subtitle_text, req.question)):
            # 客户端断连保护：与 _summarize_stream 一致，避免继续白做 LLM 调用。
            if await request.is_disconnected():
                return
            yield ServerSentEvent(data=json.dumps(token, ensure_ascii=False), event="answer")

        quota_info = {"remaining": remaining, "limit": FREE_DAILY_SUMMARY_LIMIT}
        yield ServerSentEvent(data=json.dumps(quota_info, ensure_ascii=False), event="quota")

        yield ServerSentEvent(data="[DONE]", event="done")

    except asyncio.TimeoutError:
        yield ServerSentEvent(
            data=json.dumps({"message": "回答失败: 字幕提取超时，请稍后重试"}, ensure_ascii=False),
            event="error",
        )
    except Exception as e:
        yield ServerSentEvent(
            data=json.dumps({"message": f"回答失败: {str(e)}"}, ensure_ascii=False),
            event="error",
        )


@router.post("/chat")
async def chat_with_video(
    req: ChatRequest,
    request: Request,
    user: dict | None = Depends(get_optional_user),
):
    """AI 视频问答（SSE 流式）"""
    return EventSourceResponse(_chat_stream(req, user, request))
