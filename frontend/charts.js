// charts.js
const Charts = (function(){
  function renderEdgeChart(games){
    const ctx = document.getElementById("edgeChart").getContext("2d");
    const labels = games.map(g => g.matchup);
    const data = games.map(g => (g.edge*100).toFixed(1));
    new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{ label: "Edge %", data, backgroundColor: data.map(d => d>12? 'rgba(16,185,129,0.8)' : 'rgba(59,130,246,0.8)') }]
      },
      options: {responsive:true, scales:{y:{beginAtZero:true}}}
    });
  }

  return { renderEdgeChart };
})();
