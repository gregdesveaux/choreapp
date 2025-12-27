const choreList = document.getElementById("chore-list");
const banner = document.getElementById("banner");
const refreshButton = document.getElementById("refresh");

refreshButton.addEventListener("click", () => loadChores());

function setBanner(message, tone = "info") {
  banner.textContent = message;
  banner.dataset.tone = tone;
}

function relativeTime(date) {
  const now = Date.now();
  const delta = date.getTime() - now;
  const absHours = Math.round(Math.abs(delta) / 36e5);
  if (Math.abs(delta) < 60_000) return "now";
  if (delta < 0) return `${absHours}h overdue`;
  return `in ${absHours}h`;
}

function renderChores(chores) {
  choreList.innerHTML = "";
  if (!chores.length) {
    choreList.innerHTML = `<p class="eyebrow">No chores have been set up yet.</p>`;
    return;
  }

  chores.forEach((chore) => {
    const dueDate = new Date(chore.dueDate);
    const card = document.createElement("article");
    card.className = "chore";

    const meta = document.createElement("div");
    meta.className = "chore__meta";

    const title = document.createElement("h3");
    title.className = "chore__title";
    title.textContent = chore.name;
    meta.appendChild(title);

    const details = document.createElement("div");
    details.className = "chore__details";
    details.innerHTML = `
      <span class="badge">${chore.assignedTo.name}</span>
      <span class="badge">Every ${chore.frequencyDays} day${chore.frequencyDays === 1 ? "" : "s"}</span>
      <span class="badge">Due ${dueDate.toLocaleString()}</span>
      <span class="badge badge--success">${relativeTime(dueDate)}</span>
    `;

    if (chore.isOverdue) {
      details.querySelector(".badge--success").className = "badge badge--danger";
    } else if (chore.isDueSoon) {
      details.querySelector(".badge--success").className = "badge badge--warning";
    }

    meta.appendChild(details);
    card.appendChild(meta);

    const button = document.createElement("button");
    button.textContent = "Mark done & swap";
    button.addEventListener("click", () => completeChore(chore.id, button));
    card.appendChild(button);

    choreList.appendChild(card);
  });
}

async function loadChores() {
  try {
    const response = await fetch("/api/chores");
    if (!response.ok) throw new Error("Failed to fetch chores");
    const data = await response.json();
    renderChores(data.chores ?? []);
    setBanner(`Last updated ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    console.error(error);
    setBanner("Unable to load chores right now.", "error");
  }
}

async function completeChore(choreId, button) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Working...";
  try {
    const response = await fetch(`/api/chores/${choreId}`, { method: "POST" });
    if (!response.ok) throw new Error("Failed to complete chore");
    await loadChores();
    setBanner("Chore marked complete and reassigned.", "success");
  } catch (error) {
    console.error(error);
    setBanner("We couldn't update that chore.", "error");
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

loadChores();
setInterval(loadChores, 60_000);
