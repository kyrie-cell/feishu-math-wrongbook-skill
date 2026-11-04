---
name: feishu-math-wrongbook
description: >-
  Manage a primary-school (Grade 2) math wrong-question book in Feishu Bitable
  with zero-album mobile web camera capture, CLI direct upload, Feishu Webhook
  notifications, multimodal AI visual diagnosis, and background Ebbinghaus
  spaced-repetition PDF generation. Use this skill whenever the user wants to
  start the mobile capture page, upload or analyze math wrong questions, push
  Feishu notifications, generate daily Ebbinghaus review PDFs, or update
  mastery status in Feishu Bitable.
---

# Feishu Math Wrong-Question Book & Ebbinghaus Review Skill

This skill provides a streamlined workflow for recording, diagnosing, and reviewing elementary school math wrong questions in **Feishu Bitable (飞书多维表格)**:

1. **Zero-Album Mobile Camera Web Upload**: Parents open a lightweight mobile webpage, snap a photo of a wrong question in browser RAM (`<canvas>`), and stream it directly to the CLI without cluttering the phone's photo album.
2. **Monthly Sheet Organization**: Automatically creates/uses monthly sheets (e.g., `2026年11月`, `2026年12月`) with 6 clean columns: `编号/备注`, `错题图片`, `题目（文字版）`, `题目知识点`, `深度诊断`, and `掌握程度`.
3. **Feishu Group Webhook Alerts**: Sends interactive cards to the family Feishu group when new photos are uploaded, when AI diagnosis finishes, and when daily review PDFs are ready.
4. **Multimodal AI Visual OCR & Diagnosis**: Instead of fragile standalone text OCR that loses vertical math alignment (竖式), clock faces, or ruler marks, the agent visually inspects the downloaded image, extracts the clean problem text, tags Grade 2 math knowledge points, diagnoses the root cause, and writes them back via CLI.
5. **Background Ebbinghaus Spaced Repetition**: Tracks review intervals (`1, 2, 4, 7, 15, 30` days) in `ebbinghaus_db.json`, generates printable PDF worksheets, and updates the `掌握程度` column in Feishu (`🔴 待攻克` -> `🟡 复习巩固中` -> `🟢 已掌握`).

---

## Configuration (`.env`)

Ensure the workspace `.env` file contains:

```ini
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_APP_TOKEN=xxxxxxxxxxxxxxxxxxxx
FEISHU_BITABLE_URL=https://xxx.feishu.cn/base/xxxxxxxxxxxxxxxxxxxx
# Optional: Feishu Custom Bot Webhook URL for group notifications
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## Workflows & Commands

All operations are encapsulated in [feishu_wrongbook_cli.py](./scripts/feishu_wrongbook_cli.py) and [capture_server.py](./scripts/capture_server.py).

### 1. Start the Mobile Camera Direct-Upload Webpage (No Phone Album Storage)

Run the web capture server using [capture_server.py](./scripts/capture_server.py):

```powershell
python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py serve --port 8765
```

- Serves [capture.html](./resources/capture.html) on `http://<LAN_IP>:8765`.
- Compresses captured photos in browser `<canvas>` memory and posts directly to `/api/upload`, writing to the current month's Feishu Bitable sheet and triggering the Feishu Webhook.

### 2. Direct CLI Image Upload

To upload a local image file directly to Feishu Bitable and fire a Webhook notification:

```powershell
python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py upload --image "path/to/photo.jpg" --note "竖式退位"
```

### 3. Scan & Visually Diagnose Newly Uploaded Wrong Questions

1. Fetch rows that have `错题图片` uploaded but no `深度诊断` yet:
   ```powershell
   python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py pending
   ```
2. For each item returned, use `read_file` on `local_image` to visually inspect the printed math problem, diagrams, and the child's handwritten mistake.
3. Write the extracted text, knowledge tags, deep diagnosis, and 2 variation problems back to Feishu Bitable and register the Ebbinghaus schedule:
   ```powershell
   python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py analyze `
     --record-id "<record_id>" `
     --question "<extracted clean question text + child's wrong answer>" `
     --tags "100以内退位减法,竖式计算" `
     --diagnosis "【错因】个位不够减向十位借1后，十位计算时忘记减退位点1。\n【正确解法】..." `
     --variations-json "[{\"q\": \"变式题1...\", \"a\": \"答案1\"}, {\"q\": \"变式题2...\", \"a\": \"答案2\"}]"
   ```

### 4. Generate Daily Ebbinghaus Review PDF & Notify Group

To generate today's printable review worksheet (`HTML` + `PDF` via headless Edge) and send a Feishu Webhook reminder:

```powershell
python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py due --days 0
```

### 5. Update Mastery Level After Review

When the user reports whether the child solved a reviewed problem correctly (`pass`) or incorrectly (`fail`):

```powershell
python .agents/skills/feishu-math-wrongbook/scripts/feishu_wrongbook_cli.py mastery --record-id "<record_id>" --result pass
```

- `pass`: Advances the Ebbinghaus stage in `ebbinghaus_db.json` and updates Feishu Bitable `掌握程度` to `🟡 复习巩固中` (stage 1) or `🟢 已掌握` (stage >= 2).
- `fail`: Resets Ebbinghaus stage to Day 1 and sets `掌握程度` back to `🔴 待攻克`.
