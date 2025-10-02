/* playerProps.js */
const PlayerProps = (function(){
  async function getPicksAndProps(){
    // backend endpoint returns picks + candidate props computed server-side
    return await window.AppAPI.apiGet("/api/picks_props");
  }

  function renderPropCard(p){
    const el = document.createElement("div");
    el.className = "prop";
    const confColor = p.confidence > 0.7 ? "#06f6b5" : (p.confidence > 0.5 ? "#ffcf33" : "#ff6b6b");
    el.innerHTML = `
      <h4>${p.player} — <small>${p.team}</small></h4>
      <div><strong>${p.prop_name}</strong> • Line: ${p.line} • Model: ${ (p.model_ev*100).toFixed(1) }% • Confidence: <span style="color:${confColor}">${(p.confidence*100).toFixed(0)}%</span></div>
      <div class="small">Why: ${p.justification}</div>
    `;
    return el;
  }

  async function render(){
    const grid = document.getElementById("props-grid");
    grid.innerHTML = "Loading props…";
    try{
      const data = await getPicksAndProps();
      grid.innerHTML = "";
      if(!data.props || data.props.length===0){
        grid.innerHTML = "<p>No props available today.</p>"; return;
      }
      // sort by confidence
      data.props.sort((a,b)=>b.confidence - a.confidence);
      for(const p of data.props){
        grid.appendChild(renderPropCard(p));
      }
    } catch(e){
      console.error(e);
      grid.innerHTML = "<p>Error loading props.</p>";
    }
  }
  return { render };
})();

window.PlayerProps = PlayerProps;
