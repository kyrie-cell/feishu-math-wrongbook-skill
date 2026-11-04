#!/usr/bin/env python3
"""
二年级数学错题本 CLI (Feishu Bitable + Webhook + Ebbinghaus Review)
支持：
1. 内存流/命令行直接上传错题图片写入飞书当月 Sheet（无需存手机相册）
2. 飞书群自定义机器人 Webhook 实时提醒（上传提醒、AI诊断完成提醒、每日复习提醒）
3. AI 视觉识别结果回填（题目文字版、题目知识点、深度诊断）
4. 后台艾宾浩斯遗忘曲线管理与每日复习卷生成、掌握程度联动更新
"""

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# 自动定位工作区根目录（兼容从仓库根目录或 .agents/skills/.../scripts 运行）
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
WORKSPACE_ROOT = (
    SKILL_DIR.parent.parent.parent
    if SKILL_DIR.parent.name == "skills"
    else Path.cwd()
)

ENV_PATH = WORKSPACE_ROOT / ".env"
DB_PATH = WORKSPACE_ROOT / "ebbinghaus_db.json"
UPLOADS_DIR = WORKSPACE_ROOT / "uploads"
REVIEWS_DIR = WORKSPACE_ROOT / "daily_reviews"

REVIEW_INTERVALS = [1, 2, 4, 7, 15, 30]

MONTHLY_SIMPLE_FIELDS: List[Dict[str, Any]] = [
    {"field_name": "编号/备注", "type": 1},
    {"field_name": "错题图片", "type": 17},
    {"field_name": "题目（文字版）", "type": 1},
    {
        "field_name": "题目知识点",
        "type": 4,
        "property": {
            "options": [
                {"name": "长度单位(厘米与米)"},
                {"name": "断尺测量与线段"},
                {"name": "100以内进位加法"},
                {"name": "100以内退位减法"},
                {"name": "连加连减与加减混合"},
                {"name": "求比一个数多/少几"},
                {"name": "连续两问应用题"},
                {"name": "角的认识(直角/锐角/钝角)"},
                {"name": "拼角与数角问题"},
                {"name": "乘法的意义(几个几)"},
                {"name": "2~6乘法口诀与应用"},
                {"name": "7~9乘法口诀与应用"},
                {"name": "乘加与乘减运算"},
                {"name": "够不够/能不能比较问题"},
                {"name": "排队与间隔问题"},
                {"name": "观察物体(不同位置视图)"},
                {"name": "认识时间(几时几分/经过时间)"},
                {"name": "搭配问题(排列与组合)"},
                {"name": "错中求解/思维拓展"},
            ]
        },
    },
    {"field_name": "深度诊断", "type": 1},
    {
        "field_name": "掌握程度",
        "type": 3,
        "property": {
            "options": [
                {"name": "🔴 待攻克"},
                {"name": "🟡 复习巩固中"},
                {"name": "🟢 已掌握"},
            ]
        },
    },
    {
        "field_name": "上传日期",
        "type": 5,
        "property": {"date_formatter": "yyyy/MM/dd", "auto_fill": True},
    },
]


def load_env(env_path: Path = ENV_PATH) -> Dict[str, str]:
    env_vars: Dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            env_vars[k] = v
            if k not in os.environ or not os.environ[k]:
                os.environ[k] = v
    return env_vars


def save_env_value(key: str, value: str, env_path: Path = ENV_PATH) -> None:
    if not env_path.exists():
        env_path.write_text(f"{key}={value}\n", encoding="utf-8")
        return
    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines = []
    for line in lines:
        s = line.strip()
        if not s.startswith("#") and "=" in s:
            k, _ = s.split("=", 1)
            if k.strip() == key:
                new_lines.append(f"{key}={value}")
                updated = True
                continue
        new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def send_feishu_webhook(title: str, markdown_body: str, button_url: str = "") -> bool:
    """通过飞书群自定义机器人 Webhook 发送交互式消息卡片"""
    load_env()
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False

    elements: List[Dict[str, Any]] = [
        {"tag": "markdown", "content": markdown_body},
    ]
    if button_url:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📖 打开飞书数学错题本"},
                        "type": "primary",
                        "url": button_url,
                    }
                ],
            }
        )

    card_payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": elements,
        },
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(card_payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("code", 0) == 0 or res.get("StatusCode", 0) == 0
    except Exception:
        return False


class WrongbookCLI:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self) -> None:
        load_env()
        self.app_id = os.environ.get("FEISHU_APP_ID", "").strip()
        self.app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
        self.app_token = os.environ.get("FEISHU_APP_TOKEN", "").strip()
        self.bitable_url = os.environ.get("FEISHU_BITABLE_URL", "").strip()
        if not self.app_id or not self.app_secret:
            raise RuntimeError("请先在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        self._token: Optional[str] = None
        self._expire: float = 0.0
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        REVIEWS_DIR.mkdir(parents=True, exist_ok=True)

    def get_token(self) -> str:
        now = time.time()
        if self._token and now < self._expire - 60:
            return self._token
        res = self._request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            payload={"app_id": self.app_id, "app_secret": self.app_secret},
            auth=False,
        )
        self._token = res["tenant_access_token"]
        self._expire = now + int(res.get("expire", 7200))
        return self._token

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        auth: bool = True,
    ) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if auth:
            headers["Authorization"] = f"Bearer {self.get_token()}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            res = json.loads(body) if body else {}
        if res.get("code", 0) != 0:
            raise RuntimeError(f"Feishu API Error ({path}): {res}")
        return res

    def ensure_month_sheet(self, month_name: Optional[str] = None) -> Tuple[str, str]:
        """确保当月 Sheet（如 2026年11月）存在，返回 (table_id, month_name)"""
        target = month_name or datetime.now().strftime("%Y年%m月")
        res = self._request("GET", f"/bitable/v1/apps/{self.app_token}/tables")
        tables = res.get("data", {}).get("items", []) or []
        for t in tables:
            if t.get("name") == target:
                return t["table_id"], target
        created = self._request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables",
            payload={
                "table": {
                    "name": target,
                    "default_view_name": "本月错题",
                    "fields": MONTHLY_SIMPLE_FIELDS,
                }
            },
        )
        t_id = created["data"]["table_id"]
        save_env_value("FEISHU_CURRENT_MONTH_TABLE", t_id)
        return t_id, target

    def upload_image_bytes(self, image_bytes: bytes, filename: str = "wrong_question.jpg") -> str:
        """直接将内存中的图片字节上传到飞书多维表格，返回 file_token"""
        mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
        boundary = f"----FeishuBoundary{uuid.uuid4().hex}"

        def _part(name: str, val: str) -> bytes:
            return (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{val}\r\n"
            ).encode("utf-8")

        body = bytearray()
        body.extend(_part("file_name", filename))
        body.extend(_part("parent_type", "bitable_image"))
        body.extend(_part("parent_node", self.app_token))
        body.extend(_part("size", str(len(image_bytes))))
        body.extend(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8")
        )
        body.extend(image_bytes)
        body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

        url = f"{self.BASE_URL}/drive/v1/medias/upload_all"
        headers = {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        req = urllib.request.Request(url, data=bytes(body), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        if res.get("code", 0) != 0:
            raise RuntimeError(f"上传图片附件失败: {res}")
        return res["data"]["file_token"]

    def upload_wrong_question(
        self,
        image_bytes: bytes,
        note: str = "",
        filename: str = "capture.jpg",
    ) -> Dict[str, Any]:
        """直接将错题图片写入当月飞书表，保留一份待分析缓存，并发送飞书 Webhook 提醒"""
        table_id, month_sheet = self.ensure_month_sheet()
        file_token = self.upload_image_bytes(image_bytes, filename=filename)

        now_str = datetime.now().strftime("%m%d-%H%M")
        note_id = f"{now_str}" + (f" ({note})" if note else "")

        fields: Dict[str, Any] = {
            "编号/备注": note_id,
            "错题图片": [{"file_token": file_token}],
            "掌握程度": "🔴 待攻克",
            "上传日期": int(time.time() * 1000),
        }
        res = self._request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
            payload={"fields": fields},
        )
        record_id = res["data"]["record"]["record_id"]

        # 保存一份本地待识别缓存供 AI 读取，识别后可自动清理
        local_img = UPLOADS_DIR / f"{record_id}.jpg"
        local_img.write_bytes(image_bytes)

        webhook_ok = send_feishu_webhook(
            title="📸 新数学错题已上传！",
            markdown_body=(
                f"**归档月表**：`{month_sheet}`\n"
                f"**记录编号**：`{note_id}`\n"
                f"**当前状态**：图片已直传飞书表格，等待 AI 提取题目与深度诊断。"
            ),
            button_url=self.bitable_url,
        )
        return {
            "ok": True,
            "record_id": record_id,
            "table_id": table_id,
            "month_sheet": month_sheet,
            "note_id": note_id,
            "local_image": str(local_img),
            "webhook_sent": webhook_ok,
        }

    def list_pending(self, month_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出当月表中已上传错题图片、但尚未填写深度诊断的记录"""
        table_id, month_sheet = self.ensure_month_sheet(month_name)
        res = self._request(
            "GET",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
            params={"page_size": "200"},
        )
        items = res.get("data", {}).get("items", []) or []
        pending = []
        for rec in items:
            rec_id = rec["record_id"]
            f = rec.get("fields", {})
            imgs = f.get("错题图片", [])
            diag = f.get("深度诊断", "")
            if imgs and not diag:
                local_img = UPLOADS_DIR / f"{rec_id}.jpg"
                if not local_img.exists():
                    ftoken = imgs[0].get("file_token")
                    dl_url = f"{self.BASE_URL}/drive/v1/medias/{ftoken}/download"
                    req = urllib.request.Request(
                        dl_url, headers={"Authorization": f"Bearer {self.get_token()}"}
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        local_img.write_bytes(resp.read())
                pending.append(
                    {
                        "record_id": rec_id,
                        "table_id": table_id,
                        "month_sheet": month_sheet,
                        "note_id": f.get("编号/备注", ""),
                        "local_image": str(local_img),
                    }
                )
        return pending

    def load_db(self) -> Dict[str, Any]:
        if DB_PATH.exists():
            return json.loads(DB_PATH.read_text(encoding="utf-8"))
        return {"questions": {}}

    def save_db(self, db: Dict[str, Any]) -> None:
        DB_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_analysis(
        self,
        record_id: str,
        question_text: str,
        tags: List[str],
        diagnosis: str,
        variations: List[Dict[str, str]],
        table_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """将 AI 提取的题目文字版、知识点、深度诊断写入飞书，并登记后台艾宾浩斯计划"""
        t_id = table_id or self.ensure_month_sheet()[0]
        self._request(
            "PUT",
            f"/bitable/v1/apps/{self.app_token}/tables/{t_id}/records/{record_id}",
            payload={
                "fields": {
                    "题目（文字版）": question_text,
                    "题目知识点": tags,
                    "深度诊断": diagnosis,
                    "掌握程度": "🔴 待攻克",
                }
            },
        )
        db = self.load_db()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        db["questions"][record_id] = {
            "record_id": record_id,
            "table_id": t_id,
            "question_text": question_text,
            "knowledge_tags": tags,
            "diagnosis": diagnosis,
            "variations": variations,
            "stage_index": 0,
            "next_review_date": tomorrow,
            "mastery": "🔴 待攻克",
            "updated_at": int(time.time() * 1000),
        }
        self.save_db(db)

        webhook_ok = send_feishu_webhook(
            title="🧠 AI 错题深度诊断已完成！",
            markdown_body=(
                f"**题目（文字版）**：\n{question_text}\n\n"
                f"**核心知识点**：`{'`、`'.join(tags)}`\n"
                f"**深度诊断**：\n{diagnosis}\n\n"
                f"📅 **已排入艾宾浩斯第1轮复习**：`{tomorrow}`"
            ),
            button_url=self.bitable_url,
        )
        return {"ok": True, "record_id": record_id, "next_review_date": tomorrow, "webhook_sent": webhook_ok}

    def update_mastery(self, record_id: str, passed: bool) -> Dict[str, Any]:
        """根据复习结果修改后台艾宾浩斯进度，并同步修改飞书表格【掌握程度】"""
        db = self.load_db()
        q = db.get("questions", {}).get(record_id)
        t_id = q["table_id"] if q else self.ensure_month_sheet()[0]

        if passed:
            stage = (q.get("stage_index", 0) + 1) if q else 2
            new_mastery = "🟢 已掌握" if stage >= 2 else "🟡 复习巩固中"
            next_days = REVIEW_INTERVALS[min(stage, len(REVIEW_INTERVALS) - 1)]
            next_date = (datetime.now() + timedelta(days=next_days)).strftime("%Y-%m-%d")
        else:
            stage = 0
            new_mastery = "🔴 待攻克"
            next_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        if q:
            q["stage_index"] = stage
            q["mastery"] = new_mastery
            q["next_review_date"] = next_date
            self.save_db(db)

        self._request(
            "PUT",
            f"/bitable/v1/apps/{self.app_token}/tables/{t_id}/records/{record_id}",
            payload={"fields": {"掌握程度": new_mastery}},
        )
        send_feishu_webhook(
            title="✅ 错题掌握程度已更新",
            markdown_body=(
                f"**记录 ID**：`{record_id}`\n"
                f"**最新掌握程度**：**{new_mastery}**\n"
                f"**下次艾宾浩斯复习**：`{next_date}`"
            ),
            button_url=self.bitable_url,
        )
        return {"ok": True, "record_id": record_id, "mastery": new_mastery, "next_review_date": next_date}


    def generate_daily_review_pdf(self, include_future_days: int = 0) -> Dict[str, Any]:
        """根据后台艾宾浩斯记录，筛选今日到期错题，生成可打印的 HTML + PDF 复习卷并发送 Webhook 提醒"""
        db = self.load_db()
        cutoff = (datetime.now() + timedelta(days=include_future_days)).strftime("%Y-%m-%d")
        due_items = [
            q for q in db.get("questions", {}).values()
            if q.get("next_review_date", "9999-99-99") <= cutoff and q.get("mastery") != "🟢 已掌握"
        ]
        today_str = datetime.now().strftime("%Y%m%d")
        html_path = REVIEWS_DIR / f"今日数学复习卷_{today_str}.html"
        pdf_path = REVIEWS_DIR / f"今日数学复习卷_{today_str}.pdf"

        rows_html = []
        for idx, q in enumerate(due_items, start=1):
            tags_str = "、".join(q.get("knowledge_tags", []))
            vars_html = ""
            for v_i, v in enumerate(q.get("variations", []), start=1):
                vars_html += f"<div class='var-q'><b>【变式 {v_i}】</b> {v.get('q', '')}</div><div class='work-space'></div>"
            rows_html.append(
                f"""
                <div class="question-card">
                  <div class="q-header">第 {idx} 题 · 知识点：{tags_str} <span class="rec-id">(ID: {q['record_id']})</span></div>
                  <div class="orig-q"><b>【原题重做】</b> {q.get('question_text', '')}</div>
                  <div class="work-space"></div>
                  {vars_html}
                </div>
                """
            )

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>二年级数学·艾宾浩斯今日复习卷 ({today_str})</title>
<style>
  body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; padding: 32px; color: #111; }}
  h1 {{ text-align: center; font-size: 22px; margin-bottom: 6px; }}
  .sub {{ text-align: center; color: #555; font-size: 13px; margin-bottom: 24px; border-bottom: 2px solid #222; padding-bottom: 12px; }}
  .question-card {{ border: 1px solid #cbd5e1; border-radius: 10px; padding: 16px; margin-bottom: 20px; page-break-inside: avoid; }}
  .q-header {{ font-size: 13px; color: #1e40af; font-weight: bold; margin-bottom: 8px; }}
  .rec-id {{ float: right; color: #94a3b8; font-weight: normal; }}
  .orig-q, .var-q {{ font-size: 16px; line-height: 1.6; margin-top: 8px; }}
  .work-space {{ height: 90px; border-bottom: 1px dashed #cbd5e1; margin-bottom: 8px; }}
</style>
</head>
<body>
  <h1>📝 二年级数学 · 艾宾浩斯今日滚动复习卷</h1>
  <div class="sub">日期：{datetime.now().strftime('%Y年%m月%d日')} &nbsp;|&nbsp; 待攻克错题数：{len(due_items)} 题 &nbsp;|&nbsp; 姓名：__________</div>
  {"".join(rows_html) if rows_html else "<p style='text-align:center;'>🎉 今天没有到期的错题需要复习！</p>"}
</body>
</html>"""
        html_path.write_text(html_content, encoding="utf-8")

        # 尝试调用系统 Edge 无头模式直接渲染生成 PDF
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        edge_exe = next((p for p in edge_paths if Path(p).exists()), None)
        pdf_generated = False
        if edge_exe:
            try:
                subprocess.run(
                    [
                        edge_exe,
                        "--headless",
                        "--disable-gpu",
                        f"--print-to-pdf={pdf_path}",
                        str(html_path),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=20,
                )
                pdf_generated = pdf_path.exists()
            except Exception:
                pdf_generated = False

        webhook_ok = send_feishu_webhook(
            title=f"📅 今日艾宾浩斯数学复习提醒（共 {len(due_items)} 题）",
            markdown_body=(
                f"**今日待复习错题数**：`{len(due_items)}` 题\n"
                f"**复习卷文件**：`{pdf_path.name if pdf_generated else html_path.name}`\n"
                + "\n".join(
                    [f"- `{q['record_id']}`：{q.get('question_text', '')[:40]}..." for q in due_items]
                )
            ),
            button_url=self.bitable_url,
        )
        return {
            "ok": True,
            "due_count": len(due_items),
            "html_path": str(html_path),
            "pdf_path": str(pdf_path) if pdf_generated else None,
            "webhook_sent": webhook_ok,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="二年级数学错题本 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="确保当月 Sheet 已创建")

    p_up = sub.add_parser("upload", help="直接上传错题图片写入飞书当月表并触发 Webhook")
    p_up.add_argument("--image", required=True, help="本地图片路径")
    p_up.add_argument("--note", default="", help="备注")

    sub.add_parser("pending", help="列出待 AI 识别诊断的新错题记录")

    p_an = sub.add_parser("analyze", help="回填 AI 识别的题目文字、知识点与深度诊断")
    p_an.add_argument("--record-id", required=True)
    p_an.add_argument("--question", required=True)
    p_an.add_argument("--tags", required=True, help="逗号分隔的知识点标签")
    p_an.add_argument("--diagnosis", required=True)
    p_an.add_argument("--variations-json", default="[]")

    p_ma = sub.add_parser("mastery", help="复习后修改掌握程度 (pass/fail)")
    p_ma.add_argument("--record-id", required=True)
    p_ma.add_argument("--result", choices=["pass", "fail"], required=True)

    p_due = sub.add_parser("due", help="生成今日艾宾浩斯复习卷 PDF 并发送飞书提醒")
    p_due.add_argument("--days", type=int, default=0, help="包含未来几天内到期的题目")

    p_sv = sub.add_parser("serve", help="启动手机拍照直传网页服务（不存手机相册）")
    p_sv.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()
    cli = WrongbookCLI()

    if args.cmd == "init":
        t_id, m_name = cli.ensure_month_sheet()
        print(json.dumps({"ok": True, "table_id": t_id, "month_sheet": m_name}, ensure_ascii=False))
    elif args.cmd == "upload":
        img_path = Path(args.image)
        res = cli.upload_wrong_question(img_path.read_bytes(), note=args.note, filename=img_path.name)
        print(json.dumps(res, ensure_ascii=False))
    elif args.cmd == "pending":
        res = cli.list_pending()
        print(json.dumps({"ok": True, "count": len(res), "items": res}, ensure_ascii=False, indent=2))
    elif args.cmd == "analyze":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        variations = json.loads(args.variations_json)
        res = cli.write_analysis(args.record_id, args.question, tags, args.diagnosis, variations)
        print(json.dumps(res, ensure_ascii=False))
    elif args.cmd == "mastery":
        res = cli.update_mastery(args.record_id, passed=(args.result == "pass"))
        print(json.dumps(res, ensure_ascii=False))
    elif args.cmd == "due":
        res = cli.generate_daily_review_pdf(include_future_days=args.days)
        print(json.dumps(res, ensure_ascii=False))
    elif args.cmd == "serve":
        server_script = SCRIPT_DIR / "capture_server.py"
        subprocess.run([sys.executable, str(server_script), "--port", str(args.port)], check=True)


if __name__ == "__main__":
    main()
