/* oddsTracker.js */
const OddsTracker = (function(){
  async function getOdds(){
    return await window.AppAPI.apiGet("/api/odds");
  }
  function renderOddsTable(odds){
    const container = document.getElementById("odds-table");
    container.innerHTML = "";
    if(!odds || odds.length===0) { container.innerHTML="<p>No odds available</p>"; return; }
    odds.forEach(o => {
      const block = document.createElement("div");
      block.className = "card";
      block.innerHTML = `<h4>${o.home} vs ${o.away}</h4>
        <div><strong>Moneyline:</strong> ${o.home_ml} / ${o.away_ml}</div>
        <div><strong>Total:</strong> ${o.total}</div>
        <div><small>Source: ${o.source}</small></div>
      `;
      container.appendChild(block);
    });
  }
  async function render(){
    try{
      const odds = await getOdds();
      renderOddsTable(odds);
    } catch(e){ console.error(e); document.getElementById("odds-table").innerHTML="<p>Error loading odds</p>"; }
  }
  return { render };
})();

window.OddsTracker = OddsTracker;
