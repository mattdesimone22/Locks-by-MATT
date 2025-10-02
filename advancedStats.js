/* advancedStats.js */
const AdvancedStats = (function(){
  const radarEl = document.getElementById("advRadar");
  let radarChart = null;

  async function getTeamsList(){
    const d = await window.AppAPI.apiGet("/api/team_list");
    return d.teams || [];
  }

  async function getTeamComparison(a,b){
    const d = await window.AppAPI.apiGet(`/api/team_compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
    return d;
  }

  async function render(){
    const selA = document.getElementById("adv-team-a");
    const selB = document.getElementById("adv-team-b");
    if(selA.options.length===0){
      const teams = await getTeamsList();
      teams.forEach(t => { selA.add(new Option(t,t)); selB.add(new Option(t,t)); });
      selA.value = teams[0] || "";
      selB.value = teams[1] || teams[0] || "";
    }
    async function draw(){
      const a = selA.value, b = selB.value;
      const comp = await getTeamComparison(a,b);
      const labels = ["wRC+","xwOBA","HardHit%","K-BB%","SIERA"];
      const dsA = [ comp.a.wRC_plus, comp.a.xwOBA, comp.a.hard_hit_pct, comp.a.kbb_pct, comp.a.siera ];
      const dsB = [ comp.b.wRC_plus, comp.b.xwOBA, comp.b.hard_hit_pct, comp.b.kbb_pct, comp.b.siera ];
      if(radarChart) radarChart.destroy();
      radarChart = new Chart(radarEl.getContext("2d"), {
        type: 'radar',
        data:{ labels, datasets:[
          { label: a, data: dsA, backgroundColor:'rgba(6,246,181,0.18)', borderColor:'#06f6b5' },
          { label: b, data: dsB, backgroundColor:'rgba(59,130,246,0.12)', borderColor:'#3b82f6' }
        ]},
        options: { responsive:true }
      });
    }
    selA.onchange = draw; selB.onchange = draw;
    await draw();
  }

  return { render };
})();

window.AdvancedStats = AdvancedStats;
