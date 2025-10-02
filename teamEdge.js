/* teamEdge.js */
const TeamEdge = (function(){
  const chartEl = document.getElementById("teamEdgeChart");
  let chart = null;

  async function getTeamAdvanced(){
    // backend returns aggregated team metrics for today's matchups
    return await window.AppAPI.apiGet("/api/team_stats"); // implement on backend
  }

  function computeEdge(home, away, homePitcher, awayPitcher, oddsMarket){
    // simple calibrated scoring - replace/tune with backtest
    // lower xFIP is better, higher wRC+ is better, higher CSW% is better
    const pitchDelta = (awayPitcher.xFIP || 4.0) - (homePitcher.xFIP || 4.0);
    const hitDelta = (home.wRC_plus || 100) - (away.wRC_plus || 100);
    const bullpenDelta = (away.bullpen_xFIP || 4.0) - (home.bullpen_xFIP || 4.0);
    const parkDelta = (home.park_factor || 1.0) - (away.park_factor || 1.0);
    let score = 0.45*pitchDelta + 0.30*(hitDelta/100) + 0.15*bullpenDelta + 0.10*parkDelta;
    // convert to probability
    const prob = 1/(1+Math.exp(-2.5*score));
    return Math.max(0.01, Math.min(0.99, prob));
  }

  async function render(){
    try{
      const data = await getTeamAdvanced();
      // data.games array
      const labels = [];
      const edges = [];
      const details = [];
      for(const g of data.games){
        // each g contains home, away, homePitcher/awayPitcher metrics, market odds
        const probHome = computeEdge(g.home, g.away, g.homePitcher, g.awayPitcher, g.odds);
        const edgePct = (probHome - 0.5) * 200; // +/-
        labels.push(g.shortMatch);
        edges.push(Math.round(edgePct*10)/10);
        details.push({match:g.shortMatch, prob:probHome, reason:g.reason});
      }

      if(chart) chart.destroy();
      chart = new Chart(chartEl.getContext("2d"), {
        type: 'bar',
        data: {
          labels,
          datasets: [{ label: 'Edge % (positive = home)', data: edges, backgroundColor: edges.map(v => v>6 ? '#06f6b5' : '#5aa3ff') }]
        },
        options: { responsive:true, plugins:{legend:{display:false}}}
      });

      // explanation box
      const explain = document.getElementById("teamEdgeExplain");
      explain.innerHTML = details.map(d=>`<strong>${d.match}</strong>: model probability ${Math.round(d.prob*100)}% &nbsp; <small>${d.reason || ''}</small>`).join("<br>");
    } catch(e){
      console.error("teamEdge render error", e);
    }
  }

  return { render };
})();

// allow external call
window.TeamEdge = TeamEdge;
