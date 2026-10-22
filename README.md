# 基于LLM的智慧教学资源智能调度系统

面向课程、教师与教学管理人员的教学资源调度系统。主流程是“资源建档 → 提交时段与教学条件 → 智能推荐 → 管理员确认 → 冲突复核”。

## 功能

- 建立普通教室、实验室、教学设备和在线平台资源目录，记录容量、位置与能力标签；
- 教师提交课程活动、时间、人数、资源类型与必需能力，按账号隔离需求；
- 通过“AI 需求解析”将自然语言描述提取为待核对的结构化表单，再由教师补全时间并提交；
- 自动排除不满足容量/标签的资源以及时间冲突，结合容量余量和近期使用量评分；
- 无资源可用时，给出后续日期的替代时段；
- 配置兼容 Chat Completions 的 LLM 接口后，由模型在合法候选中辅助选择并解释建议；
- 保存推荐模式、候选评分和解释。管理员确认时重新检查硬约束，防止过期建议产生重复排程；
- 仪表盘展示可用资源、待调度需求、已确认排程以及实际 LLM 建议次数。

未配置模型时使用明确标注的“规则推荐”，不会伪称已调用 LLM。模型仅做建议，不能越过资源约束或自动确认排程。详见 [TEACHING_DESIGN.md](TEACHING_DESIGN.md)。

## 运行

需要 Python 3.13、Django 6.0.7。Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

访问 `http://127.0.0.1:8000/`，登录后由管理员先新增教学资源。已有 `venv313` 的开发机可直接执行 `start_development.bat`。首次迁移前先备份原 `db.sqlite3`。

## 启用 LLM 辅助

在启动应用的同一个终端设置以下环境变量。接口需兼容 OpenAI Chat Completions；`BASE_URL` 写到 `/v1` 即可，系统会追加 `/chat/completions`。

```powershell
$env:TEACHING_LLM_BASE_URL = 'https://你的模型服务地址/v1'
$env:TEACHING_LLM_API_KEY = '你的密钥'
$env:TEACHING_LLM_MODEL = '你的模型名称'
python manage.py runserver
```

未配置或调用失败时自动回退到规则推荐。系统不向模型传送教师账号，只传送课程活动、需求说明和已过滤的资源候选；请勿在需求说明中填写敏感个人资料。

## 项目结构与验证

- `teaching/`：新教学资源、需求、推荐、排程服务与页面；
- `inventory/`：原社团库存系统的兼容模块，保留历史数据和入口；
- `sherlock/`：沿用 Django 内部配置包名，不影响展示名称；
- `run_quality_checks.ps1`：系统检查、迁移漂移检查、测试、依赖与静态文件检查。

旧项目的 [SCOPE.md](SCOPE.md)、[DATA_MODEL.md](DATA_MODEL.md)、[PHASE3.md](PHASE3.md)、[PHASE5.md](PHASE5.md) 为历史开发记录，新的功能范围以 [TEACHING_DESIGN.md](TEACHING_DESIGN.md) 为准。

本项目保留原代码的 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。

