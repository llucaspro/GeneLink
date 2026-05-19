import os
import smtplib
import socket
import ssl
import time
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from html.parser import HTMLParser


# ── Helpers ───────────────────────────────────────────────────────────────────

class _HTMLToText(HTMLParser):
    """Strip HTML tags to produce a plain-text fallback."""
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        stripped = data.strip()
        if stripped:
            self._parts.append(stripped)

    def get_text(self):
        return "\n".join(self._parts)


def _html_to_plain(html: str) -> str:
    parser = _HTMLToText()
    parser.feed(html)
    return parser.get_text()


# ── Core send function ────────────────────────────────────────────────────────

def send_email(to_addr: str, subject: str, html_body: str, retries: int = 2) -> bool:
    """
    Send an email via SMTP. Attempts STARTTLS (port 587) first, then SSL (port 465).
    Returns True on success, False on failure with detailed error logging.
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    from_addr = os.environ.get("SMTP_FROM", "")
    smtp_user = os.environ.get("SMTP_USER", "") or from_addr
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_host or not smtp_user or not smtp_pass:
        print(f"[GeneLink][EMAIL] SMTP not configured — skipping send TO={to_addr} SUBJECT={subject!r}")
        return False
    if not from_addr:
        from_addr = smtp_user

    plain_body = _html_to_plain(html_body)

    def _build_message() -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"]          = subject
        msg["From"]             = f"GeneLink <{from_addr}>"
        msg["To"]               = to_addr
        msg["Date"]             = formatdate(localtime=False)
        msg["Message-ID"]       = make_msgid(domain=from_addr.split("@")[-1])
        msg["X-Mailer"]         = "GeneLink Mailer/2.0"
        # Helps spam filters — allows one-click unsubscribe
        msg["List-Unsubscribe"] = f"<mailto:{from_addr}?subject=unsubscribe>"
        msg["Precedence"]       = "bulk"
        # Attach plain text FIRST (RFC 2046: last part preferred by client)
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body,  "html",  "utf-8"))
        return msg

    def _try_starttls(host: str, port: int) -> bool:
        msg = _build_message()
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        return True

    def _try_ssl(host: str, port: int = 465) -> bool:
        context = ssl.create_default_context()
        msg = _build_message()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        return True

    last_error = None
    for attempt in range(1, retries + 2):   # retries+1 total attempts
        try:
            # Prefer configured port; fall back to SSL on port 465 if it is 587
            if smtp_port != 465:
                _try_starttls(smtp_host, smtp_port)
            else:
                _try_ssl(smtp_host, smtp_port)
            print(f"[GeneLink][EMAIL] Sent OK — TO={to_addr} SUBJECT={subject!r} attempt={attempt}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            # Auth errors won't be fixed by retrying
            print(f"[GeneLink][EMAIL] Auth error — check SMTP_USER/SMTP_PASS. TO={to_addr} error={e}")
            return False

        except smtplib.SMTPRecipientsRefused as e:
            # Recipient rejected by server (common with institutional/strict domains)
            print(
                f"[GeneLink][EMAIL] Recipient refused — TO={to_addr} codes={e.recipients}. "
                "The domain may block external senders or require SPF/DKIM alignment."
            )
            return False

        except smtplib.SMTPSenderRefused as e:
            print(f"[GeneLink][EMAIL] Sender refused — FROM={from_addr} code={e.smtp_code} msg={e.smtp_error}")
            return False

        except smtplib.SMTPDataError as e:
            print(f"[GeneLink][EMAIL] Data error (spam filter?) — code={e.smtp_code} msg={e.smtp_error} TO={to_addr}")
            # Try SSL fallback if we were using STARTTLS
            if smtp_port != 465:
                try:
                    _try_ssl(smtp_host, 465)
                    print(f"[GeneLink][EMAIL] SSL fallback OK — TO={to_addr}")
                    return True
                except Exception as ssl_err:
                    print(f"[GeneLink][EMAIL] SSL fallback also failed — {ssl_err}")
            return False

        except (smtplib.SMTPConnectError, socket.timeout, OSError) as e:
            last_error = e
            print(f"[GeneLink][EMAIL] Connection error attempt {attempt}/{retries+1} — {e} TO={to_addr}")
            if attempt <= retries:
                time.sleep(2 ** attempt)   # exponential back-off: 2s, 4s

        except smtplib.SMTPException as e:
            last_error = e
            print(f"[GeneLink][EMAIL] SMTP error attempt {attempt}/{retries+1} — {e} TO={to_addr}")
            if attempt <= retries:
                time.sleep(2 ** attempt)

        except Exception as e:
            last_error = e
            print(f"[GeneLink][EMAIL] Unexpected error attempt {attempt}/{retries+1} — {type(e).__name__}: {e} TO={to_addr}")
            if attempt <= retries:
                time.sleep(2 ** attempt)

    print(f"[GeneLink][EMAIL] All {retries+1} attempts failed — TO={to_addr} last_error={last_error}")
    return False


# ── Email templates ───────────────────────────────────────────────────────────

def send_researcher_welcome_email(username: str, full_name: str, to_email: str, dashboard_url: str) -> bool:
    display = full_name or username
    first = display.split()[0] if display else username
    subject = "🧬 Bem-vindo(a) ao GeneLink!"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#071e33,#1b4f72);padding:36px;text-align:center">
        <div style="background:rgba(255,255,255,.12);border:2px solid rgba(255,255,255,.25);width:64px;height:64px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:30px;margin-bottom:16px">🧬</div>
        <h1 style="color:#fff;margin:0;font-size:22px;font-weight:800">Bem-vindo(a) ao GeneLink!</h1>
        <p style="color:rgba(255,255,255,.7);margin:8px 0 0;font-size:14px">Plataforma Científica de Pesquisa Genética</p>
      </div>
      <div style="padding:36px">
        <p style="font-size:16px;color:#111827;margin-bottom:8px">Olá, <strong>{first}</strong>! 👋</p>
        <p style="color:#374151;line-height:1.7">Sua conta no <strong>GeneLink</strong> foi criada com sucesso. Você agora faz parte de uma comunidade de pesquisadores dedicada à ciência genética colaborativa.</p>

        <div style="background:#f0f7ff;border:1px solid #c7dff7;border-radius:10px;padding:20px;margin:24px 0">
          <p style="margin:0 0 10px;font-weight:700;color:#1b4f72;font-size:14px">🚀 O que você pode fazer agora:</p>
          <ul style="color:#374151;line-height:2;margin:0;padding-left:20px;font-size:14px">
            <li>🔬 Buscar genes no banco de dados <strong>NCBI Gene</strong> em tempo real</li>
            <li>🤝 Ver vagas, editais e parcerias de instituições verificadas</li>
            <li>📋 Participar do fórum científico da comunidade</li>
            <li>💬 Conectar-se com outros pesquisadores via chat</li>
            <li>🏛️ Vincular-se a uma instituição verificada</li>
          </ul>
        </div>

        <div style="text-align:center;margin:28px 0">
          <a href="{dashboard_url}" style="background:#1b4f72;color:#fff;padding:14px 36px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block">
            Acessar Meu Painel →
          </a>
        </div>

        <p style="color:#6b7280;font-size:13px">Seu nome de usuário é <strong>@{username}</strong>. Guarde bem suas credenciais de acesso.</p>
        <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
        <p style="color:#9ca3af;font-size:12px;text-align:center">GeneLink · Plataforma Científica de Pesquisa Genética<br>Este é um e-mail automático, não responda a esta mensagem.</p>
      </div>
    </div>
    """
    return send_email(to_email, subject, html)


def send_institution_pending_email(inst_name: str, cnpj: str, to_email: str, base_url: str) -> bool:
    subject = f"📋 Cadastro recebido — {inst_name} está em análise no GeneLink"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#1e3a5f,#5b21b6);padding:36px;text-align:center">
        <div style="background:rgba(255,255,255,.12);border:2px solid rgba(255,255,255,.25);width:64px;height:64px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:30px;margin-bottom:16px">🏛️</div>
        <h1 style="color:#fff;margin:0;font-size:22px;font-weight:800">Cadastro Recebido com Sucesso!</h1>
        <p style="color:rgba(255,255,255,.7);margin:8px 0 0;font-size:14px">GeneLink · Plataforma Científica de Pesquisa Genética</p>
      </div>
      <div style="padding:36px">
        <p style="font-size:16px;color:#111827;margin-bottom:8px">Olá, equipe <strong>{inst_name}</strong>!</p>
        <p style="color:#374151;line-height:1.7">Recebemos o cadastro da sua instituição no <strong>GeneLink</strong>. Nosso time de verificação irá analisar os dados enviados, incluindo a validação do CNPJ informado.</p>

        <div style="background:#fef9e7;border:1px solid #f9e79f;border-radius:10px;padding:20px;margin:24px 0">
          <p style="margin:0 0 12px;font-weight:700;color:#856404;font-size:14px">📋 Dados do cadastro recebido:</p>
          <table style="width:100%;font-size:14px;color:#374151;border-collapse:collapse">
            <tr><td style="padding:4px 0;color:#6b7280;width:130px">Instituição</td><td style="font-weight:600">{inst_name}</td></tr>
            <tr><td style="padding:4px 0;color:#6b7280">CNPJ</td><td style="font-weight:600;font-family:monospace">{cnpj}</td></tr>
            <tr><td style="padding:4px 0;color:#6b7280">Status</td><td><span style="background:#fef3c7;color:#92400e;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700">⏳ Em análise</span></td></tr>
          </table>
        </div>

        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:20px;margin:24px 0">
          <p style="margin:0 0 10px;font-weight:700;color:#166534;font-size:14px">✅ Após a aprovação, sua instituição terá acesso a:</p>
          <ul style="color:#374151;line-height:2;margin:0;padding-left:20px;font-size:14px">
            <li>🏛️ Perfil institucional com <strong>Selo Oficial GeneLink</strong></li>
            <li>📢 Mural de Parcerias — publique vagas, editais e projetos</li>
            <li>👥 Gerenciamento de pesquisadores vinculados</li>
            <li>💬 Canais institucionais exclusivos</li>
          </ul>
        </div>

        <p style="color:#374151;font-size:14px;line-height:1.7">O prazo de análise é de até <strong>5 dias úteis</strong>. Você receberá um novo e-mail assim que a verificação for concluída.</p>

        <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
        <p style="color:#9ca3af;font-size:12px;text-align:center">GeneLink · Plataforma Científica de Pesquisa Genética<br>Este é um e-mail automático, não responda a esta mensagem.</p>
      </div>
    </div>
    """
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
        <p style="color:#374151">Temos uma ótima notícia: o cadastro da <strong>{inst_name} ({inst_short})</strong> na plataforma GeneLink foi <span style="color:#16a34a;font-weight:700">aprovado com sucesso</span>.</p>
        <p style="color:#374151">Sua instituição agora conta com:</p>
        <ul style="color:#374151;line-height:1.8">
          <li>🏛️ Perfil institucional verificado com <strong>Selo Oficial GeneLink</strong></li>
          <li>👥 Gerenciamento de pesquisadores vinculados ao domínio de e-mail</li>
          <li>📚 Biblioteca compartilhada restrita entre pesquisadores da instituição</li>
          <li>📢 Mural de Parcerias e Oportunidades (vagas, projetos, editais)</li>
          <li>💬 Canais institucionais exclusivos</li>
        </ul>
        <div style="text-align:center;margin:32px 0">
          <a href="{login_url}" style="background:#16a34a;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:16px">
            Acessar Painel Institucional
          </a>
        </div>
        <p style="color:#6b7280;font-size:13px">Use o e-mail e senha cadastrados no formulário de registro para entrar. Acesse a aba <strong>"Instituição"</strong> na tela de login.</p>
        <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
        <p style="color:#9ca3af;font-size:12px;text-align:center">GeneLink · Plataforma Científica de Pesquisa Genética<br>Este é um e-mail automático.</p>
      </div>
    </div>
    """
    return send_email(to_email, subject, html)
