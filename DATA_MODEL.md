# 原社团共享物资库存与领用系统数据模型（历史）

当前教学资源调度模型见 [TEACHING_DESIGN.md](TEACHING_DESIGN.md)。以下为保留的库存兼容模型说明。

版本：V1.0

本文件描述第 3 阶段完成后的 Django 数据模型和业务落地方式。范围和业务术语以 [SCOPE.md](SCOPE.md) 为准。

## 核心实体

### 物资台账

- `Section`：物资分类
- `Space`：分类下的存放位置
- `Item`：物资台账，包含当前库存 `quantity`、计量单位 `unit`、物资类型 `material_type`、预警阈值 `warning_quantity` 和启用状态 `is_active`

### 用户与申请

- `UserProfile`：登录用户的系统角色
- `ClubMember`：社团成员业务资料，可选关联一个登录账号
- `Requisition`：领用/借用申请主单，保存申请人、用途、状态和审批时间
- `RequisitionItem`：申请明细，保存申请、批准、已出库和已归还数量

### 归还与盘点

- `ReturnRecord`：归还主单，保存归还成员、状态和验收人
- `ReturnItem`：归还明细，必须关联原领用明细，并记录数量和正常/损坏/遗失状态
- `InventoryCount`：一次盘点任务
- `InventoryCountItem`：盘点任务中的物资、系统数量、实盘数量和差异原因

### 库存追溯

- `StockTransaction`：新的统一库存流水。每条记录保存物资、流水类型、数量变化、变更后余额、操作人、来源标识、幂等键、原因和时间
- `ItemLog`：旧版本库存日志，阶段 2 保留以支持兼容和回退，不用于新增业务

## 关系

```text
Section 1 ── N Space 1 ── N Item
ClubMember 1 ── N Requisition 1 ── N RequisitionItem N ── 1 Item
ReturnRecord 1 ── N ReturnItem N ── 1 RequisitionItem
InventoryCount 1 ── N InventoryCountItem N ── 1 Item
Item 1 ── N StockTransaction
```

## 关键约束

- 同一领用单不能重复添加同一物资。
- 批准数量不大于申请数量。
- 已出库数量不大于批准数量。
- 已归还数量不大于已出库数量。
- 同一归还单不能重复添加同一出库明细。
- 库存流水数量变化不能为零。
- `StockTransaction.source_key` 用于防止同一业务操作重复记账。
- 物资、成员和已生效业务记录使用保护删除策略，历史记录不直接悬空。

## 第 3 阶段业务落地

- `inventory/services.py` 集中处理申请创建、明细增删、提交、审批、驳回、撤回和出库。
- 出库在数据库事务中锁定申请明细和物资；任一物资库存不足时整单回滚，成功重试不会重复扣减。
- 耗材出库后申请直接进入“已完成”；可重复使用物资出库后进入“已出库”，全部归还或登记损耗后才完成。
- 归还验收按“正常、损坏、遗失”记录；损坏和遗失保留归还流水及独立损耗流水，库存不被错误增加。
- 盘点单先保存账面快照，确认时要求账面未被并发改变，再将差异写入盘点调整流水。
- 物资资料编辑和 Django 管理后台均不能直接改写已有物资的当前库存；库存变更入口统一写入 `StockTransaction`。

## 迁移策略

迁移 `0017_refactor_requisition_stock_models` 新增 V1.0 模型和物资字段；迁移 `0018_migrate_legacy_inventory_data` 将旧 `Student` 映射为 `ClubMember`，并将旧 `ItemLog` 复制为 `StockTransaction`；`0019` 修正库存字段说明，`0020` 补充申请完成状态。旧模型暂不删除，旧版页面仅作管理员兼容入口，待后续切换完成后再评估清理。
