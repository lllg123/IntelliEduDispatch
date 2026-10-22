# 原社团物资项目第 5 阶段：测试和交付（历史）

当前教学资源调度的测试与演示步骤见 [TEACHING_DESIGN.md](TEACHING_DESIGN.md) 和 [DELIVERY.md](DELIVERY.md)。

## 1. 阶段目标

对第 1—4 阶段的范围、数据模型、业务服务和页面交互进行最终回归，补齐关键异常与权限边界，并形成可复用的启动、测试和验收说明。

## 2. 最终测试范围

自动化测试覆盖以下内容：

- 物资库存属性、旧版借还兼容模型和旧版页面回归；
- 领用申请的创建、提交、审批、出库、事务回滚和幂等重试；
- 可重复使用物资的分次归还、损坏登记和申请完结；
- 耗材禁止归还、归还数量不能超过未归还数量；
- 驳回原因必填、普通成员不能审批或调整库存；
- 普通成员只能查看自己的领用申请；
- 库存调整同时写入新库存流水和旧版兼容日志；
- 盘点差异、盘点幂等确认和盘点期间库存变化保护；
- 物资编辑不能通过表单覆盖当前库存，新增物资会写入初始库存流水；
- 普通成员和管理员页面访问权限、关键页面状态码和登录保护。

## 3. 一键质量检查

Windows PowerShell 在项目根目录执行：

```powershell
.\run_quality_checks.ps1
```

脚本会依次执行 `check`、迁移漂移检查、迁移计划、完整 Django 测试、`pip check` 和静态文件收集试运行。也可以手工执行：

```powershell
$python = '.\venv313\Scripts\python.exe'
& $python manage.py check
& $python manage.py makemigrations --check
& $python manage.py migrate --plan
& $python manage.py test --verbosity 1
& $python -m pip check
```

Linux/macOS 可使用同样的 Django 命令，并将解释器替换为 `.venv/bin/python` 或 `venv313/bin/python`。

## 4. 交付验收清单

### 管理员

- [ ] 能登录后台并维护分类、存放位置和物资台账；
- [ ] 能入库、登记损坏/遗失、执行库存纠正并查询统一流水；
- [ ] 能审批、驳回、出库领用申请；
- [ ] 能创建盘点单，录入实盘数量并确认差异；
- [ ] 能确认可重复使用物资的归还状态。

### 普通成员

- [ ] 能创建领用申请、添加物资、提交和撤回草稿/待审批申请；
- [ ] 只能查看自己的申请和归还单；
- [ ] 不能审批、出库、调整库存、创建盘点或进入旧版管理员借还入口；
- [ ] 对可重复使用物资可提交归还，耗材不能提交归还。

### 数据一致性

- [ ] 出库库存不足时所有明细和库存均回滚；
- [ ] 重复提交出库或确认盘点不会重复扣减/调整库存；
- [ ] 每次库存变化都有 `StockTransaction` 流水；
- [ ] 盘点期间库存发生变化时，旧盘点单不能覆盖新库存。

## 5. 运行与备份

首次部署：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

开发启动脚本会自动尝试 `.venv`、`venv313`、`venv` 三种目录。生产/局域网演示还需要 Caddy，并应通过环境变量设置正式的 `DJANGO_SECRET_KEY`。

SQLite 数据库备份应在停止应用后完成：

```powershell
Copy-Item .\db.sqlite3 .\db.sqlite3.backup-$(Get-Date -Format yyyyMMdd-HHmmss)
```

真实成员资料、密码、密钥和运行时数据库不属于交付源码，不应提交到仓库或公开报告。

## 6. 已知边界

- V1.0 面向单个社团、单个仓库、整数数量和管理员/普通成员两类角色；
- 采购、付款、多仓调拨、单位换算和第三方平台集成不在本阶段范围内；
- 旧版学生借还页面作为管理员兼容入口保留，新的业务验收以社团成员、领用申请和库存流水为准；
- 默认 SQLite 适合课程设计、单机和小规模局域网演示；多人高并发部署前应评估数据库和反向代理方案；
- 摄像头扫码在跨设备访问时需要 HTTPS 和浏览器授权。
