// The page `visualize` writes: cli/okf/navigation.py _VIZ_TEMPLATE, byte for byte.

package navigation

// vizTemplate is _VIZ_TEMPLATE: the page visualize writes, with __NAME__ and __DATA__ placeholders.
const vizTemplate = "<!doctype html><html><head><meta charset=\"utf-8\">\n" +
	"<title>OKF — __NAME__</title>\n" +
	"<script src=\"https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js\"></script>\n" +
	"<script src=\"https://cdn.jsdelivr.net/npm/marked@12/marked.min.js\"></script>\n" +
	"<style>\n" +
	" body{margin:0;font:14px/1.5 system-ui,sans-serif;display:flex;height:100vh}\n" +
	" #g{flex:1;background:#0d1117}\n" +
	" #p{width:38%;max-width:560px;overflow:auto;padding:16px 22px;border-left:1px solid #30363d;background:#161b22;color:#c9d1d9}\n" +
	" #p h1,#p h2,#p h3{color:#e6edf3} #p a{color:#58a6ff} #p code,#p pre{background:#0d1117;border-radius:6px}\n" +
	" #p pre{padding:12px;overflow:auto} #bar{padding:8px 12px;background:#161b22;color:#c9d1d9;border-bottom:1px solid #30363d}\n" +
	" #s{width:220px} .meta{color:#8b949e;font-size:12px;margin-bottom:10px}\n" +
	"</style></head><body>\n" +
	"<div style=\"flex:1;display:flex;flex-direction:column\">\n" +
	" <div id=\"bar\"><b>__NAME__</b> &nbsp; <input id=\"s\" placeholder=\"filter title/type…\"></div>\n" +
	" <div id=\"g\"></div>\n" +
	"</div>\n" +
	"<div id=\"p\"><div class=\"meta\">Klick auf einen Knoten.</div></div>\n" +
	"<script>\n" +
	"const D=__DATA__;\n" +
	"const COL={ADR:'#f78166',Service:'#3fb950',Component:'#a371f7',Template:'#d29922',Reference:'#58a6ff',Guide:'#39c5cf',Concept:'#8b949e',Pattern:'#db61a2',SOP:'#e3b341',Playbook:'#ff7b72',LessonLearned:'#7ee787',ChangeNote:'#6e7681',Decision:'#bc8cff'};\n" +
	"const cy=cytoscape({container:document.getElementById('g'),\n" +
	" elements:[...D.nodes.map(n=>({data:{id:n.id,label:n.title,type:n.type}})),\n" +
	"           ...D.edges.map(e=>({data:{source:e.source,target:e.target}}))],\n" +
	" style:[{selector:'node',style:{'background-color':n=>COL[n.data('type')]||'#8b949e','width':10,'height':10,'label':'data(label)','font-size':6,'color':'#8b949e','min-zoomed-font-size':7}},\n" +
	"        {selector:'edge',style:{'width':.6,'line-color':'#30363d','curve-style':'haystack','target-arrow-shape':'none'}},\n" +
	"        {selector:'.hl',style:{'background-color':'#e6edf3','width':16,'height':16}}],\n" +
	" layout:{name:'cose',animate:false,nodeRepulsion:8000,idealEdgeLength:60}});\n" +
	"const body=Object.fromEntries(D.nodes.map(n=>[n.id,n]));\n" +
	"cy.on('tap','node',e=>{const n=body[e.target.id()];\n" +
	" document.getElementById('p').innerHTML='<div class=\"meta\">'+n.type+' · '+e.target.id()+'</div><h1>'+n.title+'</h1>'+marked.parse(n.body||'');\n" +
	" cy.elements().removeClass('hl');e.target.addClass('hl');});\n" +
	"document.getElementById('s').addEventListener('input',ev=>{const q=ev.target.value.toLowerCase();\n" +
	" cy.nodes().forEach(n=>{const h=!q||n.data('label').toLowerCase().includes(q)||(n.data('type')||'').toLowerCase().includes(q);n.style('display',h?'element':'none');});});\n" +
	"</script></body></html>"
