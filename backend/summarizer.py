"""AI 视频总结模块：字幕提取 + DeepSeek 大模型总结"""

import json
import os
import re
import tempfile
import time
from typing import Optional

import httpx
import yt_dlp
from openai import OpenAI


def _is_bilibili_url(url: str) -> bool:
    return "bilibili.com" in url or "b23.tv" in url


def _is_douyin_url(url: str) -> bool:
    """判断是否为抖音链接"""
    douyin_domains = ["douyin.com", "iesdouyin.com", "v.douyin.com"]
    return any(d in url for d in douyin_domains)


def _parse_douyin_video_info(url: str) -> dict:
    """解析抖音视频基本信息，返回 desc 标题作为替代内容"""
    try:
        from douyin import DouyinParser
        douyin_parser = DouyinParser()
        result = douyin_parser.parse(url)
        desc = result.get("description", "")
        video_id = result.get("id", "")
        if desc:
            return {"desc": desc, "video_id": video_id}
    except Exception as e:
        print(f"解析抖音视频信息失败: {e}")
    return None


class ThinkTagFilter:
    """跨 token 边界过滤 LLM 的 <think>...</think> 思维链标签。

    用于 thinking 模型可能输出的思维链污染(原 MiniMax-M2.7 实测会输出)。
    状态机处理三类边界:
    - token 完整包含 <think>...</think> → 完全跳过
    - token 只含 <think>(开始)/ </think>(结束) → 跨 token 拼接识别
    - think 模式中所有内容丢弃(保留尾部 close_len-1 字符兜底)

    用法:
        f = ThinkTagFilter()
        for token in stream:
            visible = f.feed(token)
            if visible:
                yield visible
        leftover = f.flush()  # 兜底
    """

    THINK_OPEN = "<think>"
    THINK_CLOSE = "</think>"

    def __init__(self):
        self.in_think = False
        self.buffer = ""

    def feed(self, token: str) -> str:
        if not token:
            return ""
        text = self.buffer + token
        self.buffer = ""
        out = []
        i = 0
        n = len(text)
        close_len = len(self.THINK_CLOSE)

        while i < n:
            if self.in_think:
                idx = text.find(self.THINK_CLOSE, i)
                if idx < 0:
                    # 保留尾部 close_len-1 字符 buffer 兜底跨 token 边界
                    keep = close_len - 1
                    if n - i > keep:
                        self.buffer = text[n - keep:]
                    elif n > i:
                        self.buffer = text[i:]
                    i = n
                else:
                    self.in_think = False
                    i = idx + close_len
            else:
                idx = text.find(self.THINK_OPEN, i)
                if idx < 0:
                    tail_len = self._tail_prefix_len(text, self.THINK_OPEN, i)
                    if tail_len > 0:
                        out.append(text[i : n - tail_len])
                        self.buffer = text[n - tail_len :]
                    else:
                        out.append(text[i:])
                    i = n
                else:
                    out.append(text[i:idx])
                    self.in_think = True
                    i = idx + len(self.THINK_OPEN)

        return "".join(out)

    @staticmethod
    def _tail_prefix_len(text: str, full: str, start: int) -> int:
        """text[start:] 末尾最长、可能是 full 前缀的字符数。"""
        sub = text[start:]
        max_check = min(len(sub), len(full) - 1)
        for k in range(max_check, 0, -1):
            if sub.endswith(full[:k]):
                return k
        return 0

    def flush(self) -> str:
        """流结束兜底:in_think 中残留丢弃。"""
        leftover = ""
        if not self.in_think:
            leftover = self.buffer
        self.buffer = ""
        self.in_think = False
        return leftover


class SubtitleExtractor:
    """从视频 URL 提取平台字幕（人工字幕 > 自动字幕）"""

    PREFERRED_LANGS = ["zh-Hans", "zh", "zh-CN", "en", "ja", "ko"]
    SUBTITLE_FORMAT = "json3"

    def extract(self, url: str) -> dict:
        """
        提取视频字幕，返回:
        {
            "has_subtitle": bool,
            "language": str,
            "subtitle_type": "manual" | "auto" | "none",
            "segments": [{"start": float, "end": float, "text": str}, ...],
            "full_text": str
        }
        """
        # 抖音视频不支持字幕提取，但可以获取视频描述作为替代内容
        if _is_douyin_url(url):
            video_info = _parse_douyin_video_info(url)
            if video_info and video_info.get("desc"):
                return {
                    "has_subtitle": True,
                    "language": "zh",
                    "subtitle_type": "auto",
                    "segments": [{"start": 0, "end": 10, "text": video_info["desc"]}],
                    "full_text": video_info["desc"]
                }
            return {
                "has_subtitle": False,
                "language": "",
                "subtitle_type": "none",
                "segments": [],
                "full_text": ""
            }

        if _is_bilibili_url(url):
            result = self._extract_bilibili(url)
            if result["has_subtitle"]:
                return result

        info = self._get_video_info(url)

        manual_subs = info.get("subtitles") or {}
        auto_subs = info.get("automatic_captions") or {}

        manual_subs = {k: v for k, v in manual_subs.items() if k != "danmaku"}

        lang, sub_url, sub_type = self._pick_best_subtitle(manual_subs, auto_subs)
        if not sub_url:
            return {
                "has_subtitle": False,
                "language": "",
                "subtitle_type": "none",
                "segments": [],
                "full_text": "",
            }

        segments = self._download_and_parse(url, lang, sub_type)

        full_text = " ".join(seg["text"] for seg in segments)

        return {
            "has_subtitle": True,
            "language": lang,
            "subtitle_type": sub_type,
            "segments": segments,
            "full_text": full_text,
        }

    def _extract_bilibili(self, url: str) -> dict:
        """B 站专用字幕提取（通过 dm/view API 获取 CC 字幕和 AI 字幕）"""
        empty = {
            "has_subtitle": False, "language": "", "subtitle_type": "none",
            "segments": [], "full_text": "",
        }
        try:
            bvid = self._parse_bvid(url)
            if not bvid:
                return empty

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"https://www.bilibili.com/video/{bvid}",
            }

            view_resp = httpx.get(
                f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
                headers=headers, timeout=15,
            )
            view_data = view_resp.json().get("data", {})
            cid = view_data.get("cid")
            aid = view_data.get("aid")
            if not cid or not aid:
                return empty

            dm_resp = httpx.get(
                f"https://api.bilibili.com/x/v2/dm/view?aid={aid}&oid={cid}&type=1",
                headers=headers, timeout=15,
            )
            dm_data = dm_resp.json().get("data", {})
            subtitle_list = dm_data.get("subtitle", {}).get("subtitles", [])

            if not subtitle_list:
                return empty

            best = subtitle_list[0]
            for s in subtitle_list:
                lang = s.get("lan", "")
                if lang == "zh" or lang == "zh-Hans":
                    best = s
                    break

            sub_type = "auto" if best.get("lan", "").startswith("ai-") else "manual"

            sub_url = best.get("subtitle_url", "")
            if sub_url.startswith("//"):
                sub_url = "https:" + sub_url
            if sub_url.startswith("http://"):
                sub_url = "https://" + sub_url[7:]

            if not sub_url:
                return empty

            sub_resp = httpx.get(sub_url, headers=headers, timeout=15)
            sub_json = sub_resp.json()
            body = sub_json.get("body", [])

            segments = []
            for item in body:
                content = item.get("content", "").strip()
                if not content:
                    continue
                segments.append({
                    "start": round(item.get("from", 0), 2),
                    "end": round(item.get("to", 0), 2),
                    "text": content,
                })

            full_text = " ".join(seg["text"] for seg in segments)
            return {
                "has_subtitle": True,
                "language": best.get("lan", "zh"),
                "subtitle_type": sub_type,
                "segments": segments,
                "full_text": full_text,
            }
        except Exception:
            return empty

    @staticmethod
    def _parse_bvid(url: str) -> Optional[str]:
        m = re.search(r"(BV[a-zA-Z0-9]+)", url)
        return m.group(1) if m else None

    def _get_video_info(self, url: str) -> dict:
        # P1 修复尝试（2026-08-25 实测无效）：b站 2026 年风控已升级到 wbi 签名 + cookie 双因子，
        # 单靠浏览器 UA + Referer 仍返回 412。回滚到原配置以保持最小改动原则，
        # 真正解决需要叠加用户自传 cookie（P3，超出"不擅自新增功能/依赖"硬约束，待强哥单独议）。
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extract_flat": False,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("无法解析该视频链接")
        return info

    def _pick_best_subtitle(
        self, manual_subs: dict, auto_subs: dict
    ) -> tuple[str, Optional[str], str]:
        """按优先级选择最佳字幕，返回 (lang, url, type)"""
        for lang in self.PREFERRED_LANGS:
            if lang in manual_subs:
                formats = manual_subs[lang]
                url = self._get_format_url(formats)
                if url:
                    return lang, url, "manual"

        for lang in self.PREFERRED_LANGS:
            if lang in auto_subs:
                formats = auto_subs[lang]
                url = self._get_format_url(formats)
                if url:
                    return lang, url, "auto"

        if manual_subs:
            first_lang = next(iter(manual_subs))
            url = self._get_format_url(manual_subs[first_lang])
            if url:
                return first_lang, url, "manual"

        if auto_subs:
            first_lang = next(iter(auto_subs))
            url = self._get_format_url(auto_subs[first_lang])
            if url:
                return first_lang, url, "auto"

        return "", None, "none"

    @staticmethod
    def _get_format_url(formats: list) -> Optional[str]:
        preferred = ["json3", "srv3", "vtt", "ttml"]
        for pref in preferred:
            for fmt in formats:
                if fmt.get("ext") == pref:
                    return fmt.get("url")
        return formats[0].get("url") if formats else None

    def _download_and_parse(self, url: str, lang: str, sub_type: str) -> list[dict]:
        """通过 yt-dlp 下载字幕文件并解析为分段列表"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
                "writesubtitles": sub_type == "manual",
                "writeautomaticsub": sub_type == "auto",
                "subtitleslangs": [lang],
                "subtitlesformat": "vtt",
                "outtmpl": os.path.join(tmp_dir, "subtitle"),
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            vtt_files = [
                f for f in os.listdir(tmp_dir) if f.endswith(".vtt")
            ]
            if not vtt_files:
                return []

            vtt_path = os.path.join(tmp_dir, vtt_files[0])
            return self._parse_vtt(vtt_path)

    @staticmethod
    def _parse_vtt(filepath: str) -> list[dict]:
        """解析 VTT 字幕文件为结构化分段"""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        segments = []
        blocks = re.split(r"\n\n+", content)
        time_pattern = re.compile(
            r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
        )

        seen_texts = set()
        for block in blocks:
            lines = block.strip().split("\n")
            time_match = None
            text_lines = []
            for line in lines:
                m = time_pattern.search(line)
                if m:
                    time_match = m
                elif time_match and line.strip() and not line.strip().isdigit():
                    clean = re.sub(r"<[^>]+>", "", line.strip())
                    if clean:
                        text_lines.append(clean)

            if time_match and text_lines:
                text = " ".join(text_lines)
                if text in seen_texts:
                    continue
                seen_texts.add(text)

                start = _time_to_seconds(time_match.group(1))
                end = _time_to_seconds(time_match.group(2))
                segments.append({
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "text": text,
                })

        return segments


class VideoSummarizer:
    """使用 MiniMax API 生成视频总结、思维导图、问答"""

    def __init__(self):
        api_key = os.getenv("MINIMAX_API_KEY", "")
        if not api_key:
            raise ValueError("MINIMAX_API_KEY 环境变量未设置")
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.minimaxi.com/v1",
        )
        self.model = "MiniMax-M3"
        self.max_retries = 3
        self.retry_delay = 2

    def _retry_on_overload(self, func, *args, **kwargs):
        """重试机制，处理 529 负载过高错误"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_str = str(e)
                if "529" in error_str or "overloaded" in error_str.lower():
                    last_error = e
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise
        raise last_error

    def summarize_stream(self, subtitle_text: str, language: str = "zh"):
        """流式生成视频总结，yield 每个 token(已过滤 <think> 思维链)"""
        prompt = self._build_summary_prompt(subtitle_text, language)

        def create_completion():
            return self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._build_summary_system()},
                    {"role": "user", "content": prompt},
                ],
                stream=True,
                temperature=0.7,
                max_tokens=4096,
            )

        response = self._retry_on_overload(create_completion)
        think_filter = ThinkTagFilter()

        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                visible = think_filter.feed(delta.content)
                if visible:
                    yield visible

        # 兜底:流结束时清空残留 buffer(若仍在 think 中则丢弃)
        tail = think_filter.flush()
        if tail:
            yield tail

    def generate_mindmap(self, subtitle_text: str, language: str = "zh") -> str:
        """生成思维导图 Markdown(非流式,一次性返回,已过滤 <think> 思维链)"""
        prompt = self._build_mindmap_prompt(subtitle_text, language)

        def create_completion():
            return self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._build_mindmap_system()},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
                temperature=0.5,
                max_tokens=4096,
            )

        response = self._retry_on_overload(create_completion)
        # 非流式:整段文本一次性过滤(也按 feed+flush 走完整状态机)
        raw = response.choices[0].message.content or ""
        think_filter = ThinkTagFilter()
        visible = think_filter.feed(raw)
        tail = think_filter.flush()
        return visible + tail

    def chat_stream(self, subtitle_text: str, question: str):
        """基于视频内容的 AI 问答,流式返回(已过滤 <think> 思维链)"""
        prompt = self._build_chat_prompt(subtitle_text, question)

        def create_completion():
            return self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._build_chat_system()},
                    {"role": "user", "content": prompt},
                ],
                stream=True,
                temperature=0.7,
                max_tokens=2048,
            )

        response = self._retry_on_overload(create_completion)
        think_filter = ThinkTagFilter()

        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                visible = think_filter.feed(delta.content)
                if visible:
                    yield visible

        # 兜底:流结束时清空残留 buffer(若仍在 think 中则丢弃)
        tail = think_filter.flush()
        if tail:
            yield tail

    @staticmethod
    def _build_summary_prompt(subtitle_text: str, language: str) -> str:
        truncated = subtitle_text[:15000]
        lang_hint = "中文" if language.startswith("zh") else "与原文相同的语言"
        return f"""请对以下视频字幕内容进行深度总结分析，使用{lang_hint}输出。

## 任务要求
1. 严格基于字幕内容提炼,不臆造未提及的事实、数字、人名
2. 提炼核心观点与结论,避免堆砌细节
3. 使用 Markdown 结构化呈现,便于扫读
4. 各章节字数控制：概述 50-80 字 / 大纲每节 50-100 字 / 要点每条 20-50 字 / 总结 30-50 字

## 输出格式（严格遵循）

### 视频概述
（2-3 句话概括视频主题与核心内容）

### 内容大纲
（按时间或逻辑顺序,每个章节用 `### 章节名` + 要点列表）

### 核心知识要点
（提取最重要的观点、结论或方法,用编号列表 1. 2. 3.）

### 总结
（1-2 句话给出一句话总结或核心观点）

---
视频字幕内容：
{truncated}"""

    @staticmethod
    def _build_mindmap_prompt(subtitle_text: str, language: str) -> str:
        truncated = subtitle_text[:15000]
        lang_hint = "中文" if language.startswith("zh") else "与原文相同的语言"
        return f"""请将以下视频字幕内容整理为思维导图结构，使用{lang_hint}输出。

## 任务要求
1. 使用 Markdown 标题层级（# 一级 / ## 二级 / ### 三级 / #### 四级）
2. **节点文字简洁精炼**：每个节点标题 ≤ 12 字,避免长句
3. **层级深度合理**：通常 3-4 层,过深（>5 层）会破坏可读性
4. **MECE 原则**：同级节点相互独立、穷尽覆盖,避免内容重叠
5. 只输出 Markdown 标题层级结构,不要任何说明性文字、代码块包裹或列表标记

## 结构建议
- `#` 根节点：视频核心主题
- `##` 第二层：主要章节/模块（通常 3-6 个）
- `###` 第三层：各章节核心要点（每章节 2-5 个）
- `####` 第四层：可选,用于关键概念的细节展开

---
视频字幕内容：
{truncated}"""

    @staticmethod
    def _build_chat_prompt(subtitle_text: str, question: str) -> str:
        truncated = subtitle_text[:12000]
        return f"""以下是一个视频的字幕内容，请根据这些内容回答用户的问题。

## 任务要求
1. 优先基于字幕内容作答,可适当引用原文（用引号标注）
2. 若字幕未涉及该问题,明确说明「视频内容未涉及」并简要说明理由
3. 回答简洁明了,避免冗长,优先使用列表/小标题组织
4. 严禁编造未提及的人物、数字、事实或观点
5. 如问题涉及多角度,可分点对比说明

## 输出格式
- 答案开头不要寒喧,直接给出结论
- 关键信息使用加粗 `**关键词**` 突出
- 引用原文时用 `> 引用文本` 形式

---
视频字幕内容：
{truncated}

---
用户问题：{question}"""

    # ===== System prompt 构建器 =====
    # 把角色定位 + 行为准则 + 输出约束集中到 system,user prompt 只负责具体任务描述。
    # 优化方向：从"你是一个 XXX"单句 → 加入身份边界 + 行为准则 + 输出约束三段式。

    @staticmethod
    def _build_summary_system() -> str:
        return """你是一名资深视频内容分析师,擅长从长视频字幕中提炼结构化、可执行的总结。

## 身份边界
- 只基于提供的字幕内容作答,绝不引用视频外的常识或臆测
- 你是分析者,不是评论者,保持客观中立
- 字幕不清晰时,以"原文不清晰"标注,不要推测

## 行为准则
1. 优先提取可执行的方法论、关键数据、核心观点
2. 区分"事实陈述"与"演讲者观点",用 Markdown 加粗区分
3. 合并相似观点,删除冗余的过渡性口语
4. 保留必要的原话引用（用 `>` 块引用）增强说服力

## 输出约束
- 使用 Markdown 标题与列表,层级不超过 3 级
- 全文不超过 1500 字（结构化压缩,不堆砌）
- 严格遵循 user prompt 中指定的输出格式模板"""

    @staticmethod
    def _build_mindmap_system() -> str:
        return """你是一名思维导图设计师,擅长将长文本压缩为层级清晰的视觉化结构。

## 身份边界
- 只输出 Markdown 标题层级结构（# / ## / ### / ####）
- 不要输出代码块、列表标记、说明性文字
- 不要编造字幕中未提及的章节

## 行为准则
1. 节点文字 ≤ 12 字,简洁精炼,便于一眼扫读
2. 同级节点遵循 MECE 原则（相互独立、穷尽覆盖）
3. 层级深度 3-4 层最佳,避免过深破坏可读性
4. 根节点（#）必须是视频主题,而非"思维导图"这种容器词
6. 叶子节点（最底层）必须是可独立理解的最小知识点

## 输出约束
- 只输出 Markdown 标题,前后无空行外的任何字符
- 总节点数控制在 30-50 个,过多则合并
- Markdown 渲染后将作为可视化思维导图,层级即视觉层级"""

    @staticmethod
    def _build_chat_system() -> str:
        return """你是一名视频内容问答助手,根据用户提供的视频字幕精准作答。

## 身份边界
- 回答范围严格限定在提供的字幕内容
- 字幕未涉及的问题,明确告知"视频内容未涉及",不编造答案
- 你是检索者而非创造者,引用而非生成

## 行为准则
1. 优先引用字幕原文作答,使用 `> 引用` 块引用
2. 答案开头直接给结论,不寒喧
3. 关键信息用 `**加粗**` 突出
4. 如问题涉及对比或多角度,使用列表分点说明
5. 严禁编造字幕未提及的人物、数字、日期、因果关系

## 输出约束
- 回答不超过 300 字,简洁有力,优先条理化呈现
- 引用原文不超过 50 字/次,避免大段堆砌
- 不输出"好的""当然"等客套话"""


def _time_to_seconds(time_str: str) -> float:
    """将 HH:MM:SS.mmm 转为秒数"""
    parts = time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds
