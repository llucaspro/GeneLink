document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;
  injectNavbar("/profile");
  await loadProfile();
});

async function loadProfile() {
  try {
    const res = await apiFetch("/user");
    const user = await res.json();
    setAuth(getToken(), user);
    populateView(user);
    populateForm(user);
  } catch {
    document.getElementById("profile-error").textContent =
      "Falha ao carregar dados do perfil.";
    document.getElementById("profile-error").style.display = "block";
  }
}

function populateView(u) {
  document.getElementById("profile-initials").textContent = u.avatar_initials || "?";
  document.getElementById("profile-username").textContent = `@${u.username}`;
  document.getElementById("profile-fullname").textContent = u.full_name || "—";
  document.getElementById("profile-email").textContent = u.email;
  document.getElementById("profile-institution").textContent = u.institution || "—";
  document.getElementById("profile-area").textContent = u.research_area || "—";
  document.getElementById("profile-bio").textContent = u.bio || "Nenhuma biografia fornecida.";
  document.getElementById("profile-joined").textContent = u.created_at
    ? formatDate(u.created_at)
    : "—";
}

function populateForm(u) {
  document.getElementById("edit-fullname").value = u.full_name || "";
  document.getElementById("edit-institution").value = u.institution || "";
  document.getElementById("edit-area").value = u.research_area || "";
  document.getElementById("edit-bio").value = u.bio || "";
}

function toggleEdit() {
  const form = document.getElementById("edit-form");
  const placeholder = document.getElementById("placeholder-col");
  const btn = document.getElementById("edit-toggle-btn");
  const showing = form.style.display !== "none";
  form.style.display = showing ? "none" : "block";
  placeholder.style.display = showing ? "block" : "none";
  btn.textContent = showing ? "Editar Perfil" : "Cancelar";
}

function repeatTutorial() {
  // Remove o estado salvo de ambos os tipos de tutorial
  localStorage.removeItem("gl_tut_researcher_v1");
  localStorage.removeItem("gl_tut_inst_v1");
  // Redireciona para o dashboard com flag ?tour=1 para forçar o tutorial
  window.location.href = "/gl/dashboard?tour=1";
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const alertEl = document.getElementById("profile-alert");
    const btn = document.getElementById("save-profile-btn");
    const full_name = document.getElementById("edit-fullname").value.trim();
    const institution = document.getElementById("edit-institution").value.trim();
    const research_area = document.getElementById("edit-area").value.trim();
    const bio = document.getElementById("edit-bio").value.trim();

    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Salvando…`;
    hideAlert(alertEl);

    try {
      const res = await apiFetch("/user/profile", {
        method: "PUT",
        body: JSON.stringify({ full_name, institution, research_area, bio }),
      });
      const data = await res.json();
      if (!res.ok) {
        showAlert(alertEl, data.error || "Falha ao atualizar", "error");
        return;
      }
      setAuth(getToken(), data);
      populateView(data);
      showAlert(alertEl, "Perfil atualizado com sucesso.", "success");
      document.getElementById("edit-form").style.display = "none";
      document.getElementById("placeholder-col").style.display = "block";
      document.getElementById("edit-toggle-btn").textContent = "Editar Perfil";
    } catch {
      showAlert(alertEl, "Requisição falhou. Tente novamente.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "Salvar Alterações";
    }
  });
});
