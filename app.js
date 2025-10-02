/* app.js - frontend orchestrator */
const API_BASE = ""; // empty if backend serves at same origin, or "https://yourserver.com" if remote

// UI: navigation
document.querySelectorAll(".sb-nav button").forEach(btn=>{
  btn.addEventListener("click", ()=> {
    document.querySelectorAll(".sb-nav button").forEach(b=>b.classList.remove("active"));
    btn.classList.add("active");
    const t = btn.getAttribute("data-target");
    document.querySelectorAll(".page").forEach(p=>p.classList.remove("visible"));
    document.getElementById(t).classList.add("visible");
  });
});

// quick actions
document.getElementById("refresh-all").addEventListener("click", async ()=> {
  await refreshAll();
});
document.getElementById("manual-refresh").addEventListener("click", async (e)=> {
  e.preventDefault(); await refreshAll();
});
document.getElementById("open-generate").addEventListener("click", async ()=> {
  await generateNow();
});

async function apiGet(path){
  const res = await fetch(API_BASE + path);
  if(!res.ok) throw new Error("API error: " + res.status);
  return await res.json();
}

async function refreshAll(){
  try{
    document.getElementById("last-updated").innerText = "Refreshing…";
    await loadGames();
    await TeamEdge.render();
    await PlayerProps.render();
    await AdvancedStats.render();
    await OddsTracker.render();
    document.getElementById("last-updated").innerText = "Last: " + new Date().toLocaleString();
  } catch(e){
    console.error(e);
    document.getElementById("last-updated").innerText = "Last: Error";
  }
}

// generate picks now
async function generateNow(){
  try{
    const res = await fetch(API_BASE + "/api/generate_picks", { method: "POST" });
    const json = await res.json();
    alert("Picks generated for " + json.date);
    await refreshAll();
  } catch(e){
    console.error(e);
    alert("Failed to generate picks: " + e.message);
  }
}

/* loadGames used by teamEdge/playerProps */
async function loadGames(){
  const container = document.getElementById("games-list");
  container.innerHTML = "Loading schedule…";
  try{
    const data = await apiGet("/api/scoreboard");
    container.innerHTML = "";
    if(!data.events || data.events.length === 0){
      container.innerHTML = "<p>No games today.</p>";
      return;
    }
    for(const ev of data.events){
      const comp = ev.competitions[0];
      const home = comp.competitors.find(c=>c.homeAway==="home").team;
      const away = comp.competitors.find(c=>c.homeAway==="away").team;
      const homeProb = comp.competitors.find(c=>c.homeAway==="home").probablePitcher?.fullName || "TBD";
      const awayProb = comp.competitions ? comp.competitors.find(c=>c.homeAway==="away").probablePitcher?.fullName || "TBD" : "TBD";
      const start = new Date(comp.date).toLocaleString();
      const el = document.createElement("div");
      el.className = "game";
      el.innerHTML = `<strong>${away.displayName}</strong> @ <strong>${home.displayName}</strong>
        <div><small>${start}</small> • <em>${comp.venue.fullName}</em></div>
        <div><small>Pitchers: ${awayProb} vs ${homeProb}</small></div>`;
      container.appendChild(el);
    }
  } catch(e){
    container.innerHTML = "<p>Error loading games.</p>";
    console.error(e);
  }
}

// start initial refresh
refreshAll();

// Exported modules used by other frontend files
window.AppAPI = { apiGet, refreshAll, loadGames };
