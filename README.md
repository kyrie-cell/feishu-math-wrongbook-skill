# 📸 Feishu Math Wrong-Question Book & Ebbinghaus Review Skill (`feishu-math-wrongbook`)

专为小学生（二年级数学）设计的**极简飞书错题本 + 手机拍照无痕直传（不占手机相册） + 飞书群 Webhook 提醒 + AI 视觉深度诊断 + 艾宾浩斯每日复习卷生成** Skill。

## ✨ 核心特性

1. **📱 手机拍照内存直传（不存手机相册）**
   - 内置轻量级 H5 拍照页面（[`capture.html`](.agents/skills/feishu-math-wrongbook/resources/capture.html)），妈妈在手机浏览器点一下按钮即可拍照，照片直接在浏览器 `<canvas>` 内存中压缩并上传，**手机相册零残留**。
2. **📅 按月份自动分 Sheet 的极简飞书多维表格**
   - 自动按月份创建数据表（如 `2026年11月`、`2026年12月`）。
   - 仅保留最核心的 6 列：`编号/备注`、`错题图片`、`题目（文字版）`、`题目知识点`、`深度诊断`、`掌握程度`（`🔴 待攻克` / `🟡 复习巩固中` / `🟢 已掌握`）。
3. **🔔 飞书群 Webhook 实时提醒**
   - 拍照上传成功、AI 完成错题深度诊断、每日艾宾浩斯复习卷生成、掌握程度变更时，自动往家庭飞书群推送消息卡片。
4. **🧠 AI 视觉一步提取题目 + 错题诊断**
   - 直接读取错题原图（支持识别竖式计算、钟表、尺子刻度、看图列式与手写错解），提取干净文字版题目、打上知识点标签、给出错因深度诊断与同类变式题。
5. **📈 后台艾宾浩斯遗忘曲线 & 每日 PDF 复习卷**
   - 复习排期（1 / 2 / 4 / 7 / 15 / 30 天）在后台 `ebbinghaus_db.json` 自动维护，不弄乱飞书表格界面。
   - 一键生成排版干净的 A4 打印版《今日数学复习卷.pdf》，复习做对后自动把飞书表格里的【掌握程度】更新为 `🟢 已掌握`。

---

## 📂 目录结构

```text
.
├── .agents/
│   └── skills/
│       └── feishu-math-wrongbook/
│           ├── SKILL.md                        # Antigravity Skill 核心指令文件
│           ├── scripts/
│           │   ├── feishu_wrongbook_cli.py     # CLI 核心工具（上传/诊断/艾宾浩斯/Webhook）
│           │   └── capture_server.py           # 手机拍照直传 Web 服务端
│           └── resources/
│               └── capture.html                # 手机端无痕拍照直传页面（Canvas 内存压缩）
├── .env.example                                # 环境变量配置模板
└── README.md
```

---

## 🚀 快速开始

### 1. 配置 `.env`
复制 `.env.example` 为 `.env`，填入飞书应用凭证及群机器人 Webhook：
```ini
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_APP_TOKEN=xxxxxxxxxxxxxxxxxxxx
FEISHU_BITABLE_URL=https://xxx.feishu.cn/base/xxxxxxxxxxxxxxxxxxxx
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
```

### 2. 启动手机拍照直传网页
```bash
python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py serve --port 8765
```
手机连接同一 Wi-Fi（或通过内网穿透）打开终端打印的 `http://<局域网IP>:8765`，即可直接拍照上传飞书表格。

### 3. CLI 常用命令
```bash
# 直接通过 CLI 上传一张错题图并触发飞书 Webhook
python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py upload --image photo.jpg --note "退位减法"

# 查看已上传图片但待 AI 诊断的错题
python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py pending

# 生成今日艾宾浩斯复习卷 PDF 并推送群提醒
python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py due --days 0

# 孩子复习做对后，一键更新掌握程度为 🟡/🟢
python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py mastery --record-id recxxxxxx --result pass
```
