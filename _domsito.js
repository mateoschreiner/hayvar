/* Un DOM de mentira, apenas lo justo para que el script arranque y se le
   pueda pedir que navegue. No dibuja nada: sirve para ver si el enrutador
   hace lo que dice. */
function nodo(tag){
  const n={tagName:(tag||'div').toUpperCase(),_html:'',dataset:{},style:{setProperty(){}},
    children:[],attrs:{},classList:{_s:new Set(),
      add(...c){c.forEach(x=>this._s.add(x));}, remove(...c){c.forEach(x=>this._s.delete(x));},
      toggle(c,v){ v===undefined? (this._s.has(c)?this._s.delete(c):this._s.add(c)) : (v?this._s.add(c):this._s.delete(c)); },
      contains(c){return this._s.has(c);}},
    get innerHTML(){return this._html;}, set innerHTML(v){this._html=String(v);},
    textContent:'', value:'', offsetHeight:56,
    setAttribute(k,v){this.attrs[k]=v;}, getAttribute(k){return this.attrs[k];},
    appendChild(){}, remove(){}, blur(){}, focus(){},
    addEventListener(){}, querySelector(){return null;}, querySelectorAll(){return [];},
    closest(){return null;}};
  return n;
}
const porId={};
const doc={documentElement:nodo('html'), body:nodo('body'), head:nodo('head'),
  _oyentes:{},
  createElement:nodo,
  addEventListener(t,f){ (this._oyentes[t]=this._oyentes[t]||[]).push(f); },
  querySelector(s){ return porId[s]||(porId[s]=nodo()); },
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
