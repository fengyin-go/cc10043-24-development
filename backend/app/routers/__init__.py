"""业务路由汇总：规则影响明细等固定路径优先注册，再挂通用模块资源路由。"""
from __future__ import annotations

from app.routers import impact, resource

ROUTERS = [impact, resource]
