"""用户云端历史记录 API（解析/下载/总结）。

路由组统一要求登录（Depends(get_current_user)），与 api_video_cache 一致。
响应体沿用 {success, data, total}/{success, message} 风格，便于前端复用既有解析逻辑。
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from database import get_history, delete_history, clear_history

router = APIRouter(prefix="/api/history", dependencies=[Depends(get_current_user)])


class ClearRequest(BaseModel):
    pass


@router.get("")
def list_history(
    user: dict = Depends(get_current_user),
    type: str | None = Query(None, description="parse | download | summary"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    # 同步函数（FastAPI 放入线程池）：内部是同步 SQLite 查询，
    # 写成 async def 会在事件循环里执行同步 IO，阻塞其它请求。
    rows, total = get_history(user["id"], htype=type, limit=limit, offset=offset)
    return {"success": True, "data": rows, "total": total}


@router.delete("/{history_id}")
def remove_history(history_id: int, user: dict = Depends(get_current_user)):
    ok = delete_history(history_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在或无权删除")
    return {"success": True, "message": "已删除"}


@router.post("/clear")
def clear_my_history(user: dict = Depends(get_current_user)):
    clear_history(user["id"])
    return {"success": True, "message": "已清空历史记录"}
