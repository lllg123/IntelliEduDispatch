# 基于LLM的智慧教学资源智能调度系统：交付说明

## 交付内容

当前主业务为教学资源智能调度。原 `inventory` 模块用于历史数据兼容，新的功能与验收标准见 [TEACHING_DESIGN.md](TEACHING_DESIGN.md)。

重点入口：

- [README.md](README.md)：项目概览与快速启动；
- [TEACHING_DESIGN.md](TEACHING_DESIGN.md)：新调度流程、AI 模式、模型与验收；
- [SCOPE.md](SCOPE.md)、[DATA_MODEL.md](DATA_MODEL.md)：旧库存项目的历史记录；
- [run_quality_checks.ps1](run_quality_checks.ps1)：Windows 一键质量检查。

## 验收命令

在项目根目录打开 PowerShell：

```powershell
.\run_quality_checks.ps1
```

验收通过的最低条件是：Django system check 通过、没有未生成迁移、没有待执行迁移、完整测试通过、依赖检查通过。首次运行先执行 `python manage.py migrate`。

## 演示建议

1. 执行 `python manage.py migrate`；
2. 执行 `python manage.py createsuperuser` 创建管理员；
3. 执行 `.\start_development.bat`；
4. 管理员创建两间不同容量、带能力标签的教室；
5. 普通账号通过“AI 需求解析”或表单提交课程需求；
6. 生成并查看候选评分与推荐模式；
7. 管理员确认资源，再提交重叠时段需求验证冲突过滤；
8. 查看无资源时的替代时段；取消排程后验证资源重新可用。

## 交付注意事项

- 不要把 `db.sqlite3`、`.secret_key_file`、真实成员信息或导出的运行时数据提交到仓库；
- 局域网 HTTPS 启动需安装 Caddy 或将 `caddy.exe` 放入项目目录；本地 HTTP 演示使用 `start_development.bat`；
- 生产启动前设置正式 `DJANGO_SECRET_KEY` 并确认 HTTPS 配置；
- 需要回滚时，先停止应用，再用最近一次数据库备份恢复；
- 旧版社团物资库存模块仍可访问，但教学调度是当前项目的主流程。
