# 基于LLM的智慧教学资源智能调度系统页面地图

当前主页面：`/teaching/` 工作台、`/teaching/resources/` 教学资源、`/teaching/requests/` 调度需求、`/teaching/requests/assistant/` AI 需求解析。资源创建/编辑与管理员确认入口在对应页面内。`/` 和 `/dashboard/` 均进入新工作台。

下方为旧社团库存模块的历史页面地图，继续用于兼容入口。

本页面地图对应 V1.0 范围基线，详细业务边界见 [SCOPE.md](SCOPE.md)。路径仍沿用现有 Django 路由，页面名称按社团物资业务表达。

## 公开页面

- `/`：系统首页
- `/accounts/login/`：登录
- `/accounts/signup/`：注册

## 工作台

- `/dashboard/`：社团物资工作台
  - 当前借用数量
  - 逾期数量
  - 库存预警物资
  - 本月新增成员
  - 近期领用、借用和归还活动

## 物资管理

- `/browse/`：物资台账浏览
- `/sections/`：物资分类
- `/sections/<section_code>/spaces/`：分类下的存放位置
- `/sections/<section_code>/spaces/<space_code>/items/`：位置下的物资
- `/low-stock-report/`：库存预警
- `/inventory-counts/`：库存盘点单，仅管理员可访问
- `/inventory-counts/new/`：创建盘点快照
- `/inventory-counts/<count_no>/`：录入实盘数量并确认差异
- `/sections/<section_code>/spaces/<space_code>/items/<item_code>/`：物资详情和库存流水

物资资料编辑不能直接修改已有物资库存；库存变化通过管理员库存调整和核心业务服务写入流水。

## 领用与借用

- `/students/`：社团成员
- `/students/<id>/`：成员资料和历史记录
- `/checkout/`：领用/借用申请入口
- `/checkout/session/<student_id>/`：申请明细和提交
- `/on-loan/`：领用与借用记录
- `/overdue-report/`：可重复使用物资的逾期记录
- `/check-in/<log_id>/`：归还验收
- `/requisitions/`：领用申请列表；管理员查看全部，普通成员只查看自己的申请
- `/requisitions/new/`：新建领用/借用申请
- `/requisitions/<request_no>/`：申请详情、添加明细、提交、审批、出库和撤回
- `/requisitions/<request_no>/return/new/`：提交可重复使用物资归还
- `/returns/<return_no>/`：归还单详情和管理员验收

旧版 `/checkout/` 和 `/check-in/` 页面仅保留给管理员兼容历史数据；V1.0 新业务以申请单流程为准。

## 工具与报表

- `/search/`：综合搜索
- `/lookup/`：条码/二维码查询
- `/print-shop/`：标签打印
- `/print/`：标签打印队列
- `/sitemap/`：系统导航

## 用户与权限

- `/my-profile/`：个人资料
- `/team-management/`：用户与权限管理，仅管理员可访问
- `/admin/`：Django 管理后台，仅授权管理员可访问

普通成员只能处理自己的领用申请；管理员才能维护台账、处理库存、审批申请、确认归还和执行盘点。
