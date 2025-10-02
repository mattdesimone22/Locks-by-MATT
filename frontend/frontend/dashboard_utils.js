// dashboard_utils.js
const Dashboard = (function(){
  async function loadPicks(){
    try {
      const resp = await fetch("/data/picks_today.json");
      if(!resp.ok) throw new Error("Network error");
      return await resp.json();
    } catch (e) {
      console.error("Failed to load picks:", e);
      // fallback to root-level file if deployed differently
      const resp2 = await fetch("/picks_today.json");
      return await resp2.json();
    }
  }

  function renderTable(data){
    const tbody = document.querySelector("#picksTable tbody");
    tbody.innerHTML = "";
    data.games.forEach(g => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${g.matchup}<br><small>${g.pitcher_matchup || ""}</small></td>
        <td>${g.pick}</td>
        <td>${(g.edge*100).toFixed(1)}%</td>
        <td><button onclick='Dashboard.showDetails(${JSON.stringify(JSON.stringify(g)).replaceAll("'", "\\'")})'>Details</button></td>
      `;
      tbody.appendChild(tr);
    });
    document.getElementById("lastUpdated").innerText = "Last: " + (data.generated_at_utc || data.date || "");
  }

  function showDetails(jsonStr){
    const g = JSON.parse(JSON.parse(jsonStr));
    alert("Reason: " + g.reason + "\\nTeam: " + g.team_stats + "\\nPlayer props: " + JSON.stringify(g.player_stats, null, 2));
  }

  return {
    loadAndRender: async function(){
      const data = await loadPicks();
      renderTable(data);
      Charts.renderEdgeChart(data.games);
    },
    showDetails
  };
})();
