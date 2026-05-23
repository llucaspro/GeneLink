import os
import smtplib
import socket
import ssl
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from html.parser import HTMLParser


# ── Helpers ───────────────────────────────────────────────────────────────────

class _HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
    def handle_data(self, data):
        s = data.strip()
        if s:
            self._parts.append(s)
    def get_text(self):
        return "\n".join(self._parts)

def _html_to_plain(html: str) -> str:
    p = _HTMLToText(); p.feed(html); return p.get_text()


# ── Gmail / SMTP (primary) ────────────────────────────────────────────────────

def _send_via_smtp(to_addr: str, subject: str, html_body: str, retries: int = 2) -> bool:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    from_addr = os.environ.get("SMTP_FROM", "")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        return False
    if not from_addr:
        from_addr = smtp_user

    plain = _html_to_plain(html_body)

    def _msg():
        msg = MIMEMultipart("alternative")
        msg["Subject"]    = subject
        msg["From"]       = f"GeneLink <{from_addr}>"
        msg["To"]         = to_addr
        msg["Date"]       = formatdate(localtime=False)
        msg["Message-ID"] = make_msgid(domain=from_addr.split("@")[-1])
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html",  "utf-8"))
        return msg

    last_err = None
    for attempt in range(1, retries + 2):
        try:
            if smtp_port == 465:
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(smtp_host, 465, context=ctx, timeout=15) as s:
                    s.login(smtp_user, smtp_pass)
                    s.sendmail(from_addr, [to_addr], _msg().as_string())
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
                    s.ehlo(); s.starttls(); s.ehlo()
                    s.login(smtp_user, smtp_pass)
                    s.sendmail(from_addr, [to_addr], _msg().as_string())
            print(f"[GeneLink][EMAIL] SMTP OK — TO={to_addr}")
            return True
        except smtplib.SMTPAuthenticationError as e:
            print(f"[GeneLink][EMAIL] SMTP auth error — {e}")
            return False
        except (smtplib.SMTPConnectError, socket.timeout, OSError) as e:
            last_err = e
            if attempt <= retries:
                time.sleep(2 ** attempt)
        except Exception as e:
            last_err = e
            if attempt <= retries:
                time.sleep(2 ** attempt)
    print(f"[GeneLink][EMAIL] SMTP failed — TO={to_addr} err={last_err}")
    return False


# ── Resend API (fallback) ─────────────────────────────────────────────────────

def _send_via_resend(to_addr: str, subject: str, html_body: str) -> bool:
    api_key  = os.environ.get("RESEND_API_KEY", "")
    from_addr = os.environ.get("RESEND_FROM", "GeneLink <onboarding@resend.dev>")
    if not api_key:
        return False
    try:
        import urllib.request, json
        payload = json.dumps({
            "from": from_addr, "to": [to_addr],
            "subject": subject, "html": html_body,
            "text": _html_to_plain(html_body),
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails", data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            print(f"[GeneLink][EMAIL] Resend OK — id={result.get('id')} TO={to_addr}")
            return True
    except Exception as e:
        print(f"[GeneLink][EMAIL] Resend error — {e} TO={to_addr}")
        return False


# ── Public send function ──────────────────────────────────────────────────────

def send_email(to_addr: str, subject: str, html_body: str) -> bool:
    """Gmail/SMTP first, Resend as fallback."""
    if _send_via_smtp(to_addr, subject, html_body):
        return True
    if _send_via_resend(to_addr, subject, html_body):
        return True
    print(f"[GeneLink][EMAIL] No provider configured — TO={to_addr}")
    return False


# ── Templates ─────────────────────────────────────────────────────────────────

def send_institution_pending_email(inst_name: str, cnpj: str, to_email: str, base_url: str) -> bool:
    subject = f"📋 Cadastro recebido — {inst_name} está em análise no GeneLink"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#1e3a5f,#5b21b6);padding:36px;text-align:center">
        <div style="background:rgba(255,255,255,.12);width:64px;height:64px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:30px;margin-bottom:16px">🏛️</div>
        <h1 style="color:#fff;margin:0;font-size:22px;font-weight:800">Cadastro Recebido!</h1>
        <p style="color:rgba(255,255,255,.7);margin:8px 0 0;font-size:14px">GeneLink · Plataforma Científica de Pesquisa Genética</p>
      </div>
      <div style="padding:36px">
        <p style="font-size:16px;color:#111827">Olá, equipe <strong>{inst_name}</strong>!</p>
        <p style="color:#374151;line-height:1.7">Recebemos o cadastro da sua instituição no GeneLink. Nossa equipe irá analisar os dados e validar o CNPJ informado.</p>
        <div style="background:#fef9e7;border:1px solid #f9e79f;border-radius:10px;padding:20px;margin:24px 0">
          <p style="margin:0 0 12px;font-weight:700;color:#856404;font-size:14px">📋 Dados recebidos:</p>
          <table style="width:100%;font-size:14px;color:#374151;border-collapse:collapse">
            <tr><td style="padding:4px 0;color:#6b7280;width:130px">Instituição</td><td style="font-weight:600">{inst_name}</td></tr>
            <tr><td style="padding:4px 0;color:#6b7280">CNPJ</td><td style="font-family:monospace;font-weight:600">{cnpj}</td></tr>
            <tr><td style="padding:4px 0;color:#6b7280">Status</td><td><span style="background:#fef3c7;color:#92400e;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700">⏳ Em análise</span></td></tr>
          </table>
        </div>
        <p style="color:#374151;font-size:14px">Prazo de análise: até <strong>5 dias úteis</strong>. Você receberá um e-mail quando a verificação for concluída.</p>
        <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
        <p style="color:#9ca3af;font-size:12px;text-align:center">GeneLink · Este é um e-mail automático.</p>
      </div>
    </div>"""
    return send_email(to_email, subject, html)


def send_institution_approval_email(inst_name: str, inst_short: str, to_email: str, login_url: str) -> bool:
    subject = f"✅ {inst_name} foi aprovada no GeneLink!"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#1e3a5f,#2d6a4f);padding:32px;text-align:center">
        <div style="background:#22c55e;width:60px;height:60px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:16px">✅</div>
        <h1 style="color:#fff;margin:0;font-size:22px">Cadastro Aprovado!</h1>
        <p style="color:rgba(255,255,255,.8);margin:8px 0 0;font-size:14px">GeneLink · Plataforma Científica de Pesquisa Genética</p>
      </div>
      <div style="padding:32px">
        <p style="font-size:16px;color:#111">Olá, equipe <strong>{inst_name}</strong>!</p>
        <p style="color:#374151;line-height:1.7">O cadastro da <strong>{inst_name} ({inst_short})</strong> no GeneLink foi <span style="color:#16a34a;font-weight:700">aprovado com sucesso</span>! 🎉</p>
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:20px;margin:24px 0">
          <p style="margin:0 0 10px;font-weight:700;color:#166534;font-size:14px">🚀 Agora sua instituição tem acesso a:</p>
          <ul style="color:#374151;line-height:2;margin:0;padding-left:20px;font-size:14px">
            <li>🏛️ Perfil institucional verificado com <strong>Selo Oficial GeneLink</strong></li>
            <li>👥 Gerenciamento de pesquisadores vinculados</li>
            <li>📢 Mural de Parcerias e Oportunidades</li>
            <li>💬 Canais institucionais exclusivos</li>
          </ul>
        </div>
        <div style="text-align:center;margin:32px 0">
          <a href="{login_url}" style="background:#16a34a;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:16px;display:inline-block">
            Acessar Painel Institucional →
          </a>
        </div>
        <p style="color:#6b7280;font-size:13px">Use o e-mail e senha cadastrados. Na tela de login, clique na aba <strong>"Instituição"</strong>.</p>
        <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
        <p style="color:#9ca3af;font-size:12px;text-align:center">GeneLink · Este é um e-mail automático.</p>
      </div>
    </div>"""
    return send_email(to_email, subject, html)


def send_researcher_welcome_email(username: str, full_name: str, to_email: str, dashboard_url: str) -> bool:
    display = full_name or username
    first = display.split()[0] if display else username
    subject = "🧬 Bem-vindo(a) ao GeneLink!"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#071e33,#1b4f72);padding:36px;text-align:center">
        <div style="background:rgba(255,255,255,.12);width:64px;height:64px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:30px;margin-bottom:16px">🧬</div>
        <h1 style="color:#fff;margin:0;font-size:22px;font-weight:800">Bem-vindo(a) ao GeneLink!</h1>
      </div>
      <div style="padding:36px">
        <p style="font-size:16px;color:#111827">Olá, <strong>{first}</strong>! 👋</p>
        <p style="color:#374151;line-height:1.7">Sua conta no <strong>GeneLink</strong> foi criada com sucesso.</p>
        <div style="text-align:center;margin:28px 0">
          <a href="{dashboard_url}" style="background:#1b4f72;color:#fff;padding:14px 36px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block">
            Acessar Meu Painel →
          </a>
        </div>
        <p style="color:#6b7280;font-size:13px">Seu usuário: <strong>@{username}</strong></p>
        <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
        <p style="color:#9ca3af;font-size:12px;text-align:center">GeneLink · Este é um e-mail automático.</p>
      </div>
    </div>"""
    return send_email(to_email, subject, html)
