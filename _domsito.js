/* Un DOM de mentira, apenas lo justo para que el script arranque y se le
   pueda pedir que navegue. No dibuja nada: sirve para ver si el enrutador
   hace lo que dice. */
function nodo(tag){
  const n={tagName:(tag||'div').toUpperCase(),_html:'',dataset:{},style:{setProperty(){}},
    children:[],attrs:{},classList:{_s:new Set(),
      add(...c){c.forEach(x=>this._s.add(x));}, remove(...c){c.forEach(x=>this._s.delete(x));},
      toggle(c,v){ v===undefined? (this._s.has(c)?this._s.delete(c):this._s.add(c)) : (v?this._s.add(c):this._s.delete(c)); },
      contains(c){return this._s.has(c);}},
    get innerHTML(){return this._html;},
    set innerHTML(v){this._html=String(v); anotarIds(v);},
    textContent:'', value:'', offsetHeight:56,
    /* Agregar sin rehacer lo que ya está. La página lo usa para colgar el
       historial abajo de la tabla del torneo sin volver a dibujarla. Sólo
       se implementan las dos posiciones que se usan. */
    insertAdjacentHTML(donde,html){
      anotarIds(html);
      if(donde==='beforeend') this._html += String(html);
      else if(donde==='afterbegin') this._html = String(html) + this._html;
    },
    setAttribute(k,v){this.attrs[k]=v;}, getAttribute(k){return this.attrs[k];},
    appendChild(){}, remove(){}, blur(){}, focus(){},
    addEventListener(){}, querySelector(){return null;}, querySelectorAll(){return [];},
    closest(){return null;}};
  return n;
}
/* Qué elementos existen de verdad.

   Antes `querySelector` inventaba un nodo para cualquier selector, y con
   eso una pantalla podía buscar algo que todavía no se había dibujado y la
   prueba no se enteraba. Pasó de verdad: el submenú del torneo se pedía
   antes de que `shell()` armara la pantalla, en el navegador daba null y no
   se dibujaba nunca, y acá pasaba en verde.

   Ahora se lleva la cuenta de los `id` que se fueron escribiendo, y lo que
   nadie escribió no existe —igual que en un navegador—. Se anotan sólo los
   `id`: modelar clases y anidamiento sería escribir medio navegador, y con
   los id alcanza para la clase de error que importa. */
// Los que ya vienen en el HTML antes de que el script toque nada. Si
// alguna vez se agrega uno al documento de arranque, va acá.
const IDS = new Set(['app', 'bar', 'barTime', 'barTxt', 'clubCrest', 'dot',
                     'golBtn', 'liveBtn', 'liveCnt', 'modalBox', 'ov', 'q',
                     'qres', 'scrim']);
function anotarIds(html){
  for (const m of String(html || '').matchAll(/id="([^"]+)"/g)) IDS.add(m[1]);
}

const porId={};
const doc={documentElement:nodo('html'), body:nodo('body'), head:nodo('head'),
  _oyentes:{},
  createElement:nodo,
  addEventListener(t,f){ (this._oyentes[t]=this._oyentes[t]||[]).push(f); },
  querySelector(s){
    // Un id que nadie escribió no existe, igual que en el navegador.
    const m=/^#([\w-]+)$/.exec(String(s||''));
    if(m && !IDS.has(m[1])) return null;
    return porId[s]||(porId[s]=nodo());
  },
  querySelectorAll(){ return []; },
  getElementById(id){ return porId['#'+id]||(porId['#'+id]=nodo()); }};
doc.documentElement.dataset={};
const almacenLocal={_d:{},getItem(k){return this._d[k]??null;},setItem(k,v){this._d[k]=String(v);},removeItem(k){delete this._d[k];}};
const historial={_pila:[],state:null,
  pushState(s,_,u){ this._pila.push({s,u}); this.state=s; loc.pathname=u; },
  replaceState(s,_,u){ if(this._pila.length) this._pila.pop(); this._pila.push({s,u}); this.state=s; loc.pathname=u; },
  back(){ this._pila.pop(); const a=this._pila[this._pila.length-1]; 
          if(a){ this.state=a.s; loc.pathname=a.u; }
          (win._oyentes.popstate||[]).forEach(f=>f({state:this.state})); }};
const loc={pathname:'/',search:'',hash:'',origin:'http://x',href:'http://x/'};
const win={_oyentes:{}, addEventListener(t,f){ (this._oyentes[t]=this._oyentes[t]||[]).push(f); },
  location:loc, history:historial, localStorage:almacenLocal,
  ResizeObserver:null, requestAnimationFrame(f){}, setTimeout(){return 0;}, clearTimeout(){}};
class MutationObserver{ constructor(){} observe(){} }
class URL2{ constructor(u,base){ const m=/^https?:\/\/[^/]+(\/.*)?$/.exec(u); this.pathname=m?(m[1]||'/'):u; } }
async function fetchFalso(){ throw new Error('sin red en la prueba'); }
/* Los relojes también son de mentira. Sin esto, el `setInterval` que la
   página usa para avisar que la persona sigue leyendo mantiene vivo a node
   para siempre y la prueba nunca termina — me pasó, y el síntoma era que
   todo el conjunto se colgaba sin decir por qué. */
function setInterval(){ return 0; }
function clearInterval(){}
function setTimeout(){ return 0; }
function clearTimeout(){}
