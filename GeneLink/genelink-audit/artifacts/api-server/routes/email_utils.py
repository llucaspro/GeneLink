import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(to_addr: str, subject: str, html_body: str) -> bool:
    """Send email via SMTP. Returns True on success, False on failure (logs error)."""
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    from_addr = os.environ.get("SMTP_FROM", smtp_user or "noreply@genelink.app")

    if not smtp_host or not smtp_user:
        print(f"[GeneLink] EMAIL (SMTP not configured) → TO: {to_addr} | SUBJECT: {subject}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"GeneLink <{from_addr}>"
        msg["To"]      = to_addr
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        print(f"[GeneLink] Email sent → {to_addr}")
        return True
    except Exception as e:
        print(f"[GeneLink] Email error → {to_addr}: {e}")
        return False


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
