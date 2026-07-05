(function(){
  function pad(n){return n<10?'0'+n:''+n;}
  var now=new Date();
  var iso=now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate());

  // --- Quick-panel mini-kalender: hvis det udgivne HTML viser en tidligere
  // maaned (gammelt build), genopbygges gridden client-side for den aktuelle
  // maaned. Helligdage beregnes med paaske-algoritmen (som calendar-tools.js).
  function easterSunday(y){
    var a=y%19,b=Math.floor(y/100),c=y%100,d=Math.floor(b/4),e=b%4,
        f=Math.floor((b+8)/25),g=Math.floor((b-f+1)/3),
        h=(19*a+b-d-g+15)%30,i=Math.floor(c/4),k=c%4,
        l=(32+2*e+2*i-h-k)%7,m=Math.floor((a+11*h+22*l)/451),
        mo=Math.floor((h+l-7*m+114)/31),da=((h+l-7*m+114)%31)+1;
    return new Date(Date.UTC(y,mo-1,da));
  }
  function addD(dt,n){return new Date(dt.getTime()+n*86400000);}
  function isoOf(dt){return dt.getUTCFullYear()+'-'+pad(dt.getUTCMonth()+1)+'-'+pad(dt.getUTCDate());}
  function marksFor(y){
    var e=easterSunday(y),out={};
    function put(dt,name,official){out[isoOf(dt)]={n:name,o:official};}
    put(new Date(Date.UTC(y,0,1)),'Nyt\u00e5rsdag',true);
    put(addD(e,-7),'Palmes\u00f8ndag',false);
    put(addD(e,-3),'Sk\u00e6rtorsdag',true);
    put(addD(e,-2),'Langfredag',true);
    put(e,'P\u00e5skedag',true);
    put(addD(e,1),'2. p\u00e5skedag',true);
    put(addD(e,39),'Kristi himmelfartsdag',true);
    put(addD(e,49),'Pinsedag',true);
    put(addD(e,50),'2. pinsedag',true);
    put(new Date(Date.UTC(y,4,1)),'Arbejdernes kampdag',false);
    put(new Date(Date.UTC(y,5,5)),'Grundlovsdag',false);
    put(new Date(Date.UTC(y,11,24)),'Juleaftensdag',false);
    put(new Date(Date.UTC(y,11,25)),'Juledag',true);
    put(new Date(Date.UTC(y,11,26)),'2. juledag',true);
    put(new Date(Date.UTC(y,11,31)),'Nyt\u00e5rsaftensdag',false);
    return out;
  }
  function rebuildMiniCalendar(){
    var panel=document.querySelector('.quick-panel[data-auto-month]');
    if(!panel)return;
    var grid=panel.querySelector('.mini-calendar');
    if(!grid)return;
    var first=grid.querySelector('[data-date]');
    if(!first)return;
    if(first.getAttribute('data-date').slice(0,7)===iso.slice(0,7))return;
    var y=now.getFullYear(),m=now.getMonth();
    var marks=marksFor(y);
    var MDR=['Januar','Februar','Marts','April','Maj','Juni','Juli','August','September','Oktober','November','December'];
    var h2=panel.querySelector('h2');
    if(h2)h2.textContent=MDR[m]+' '+y;
    var spans=grid.querySelectorAll('span:not(.head)');
    for(var k=0;k<spans.length;k++)grid.removeChild(spans[k]);
    var lead=(new Date(Date.UTC(y,m,1)).getUTCDay()+6)%7; // man=0
    var dim=new Date(Date.UTC(y,m+1,0)).getUTCDate();
    var frag=document.createDocumentFragment();
    function span(cls,txt,dateIso,title){
      var s=document.createElement('span');
      if(cls)s.className=cls;
      if(dateIso)s.setAttribute('data-date',dateIso);
      if(title)s.title=title;
      s.textContent=txt||'';
      return s;
    }
    for(var a=0;a<lead;a++)frag.appendChild(span('empty',''));
    for(var d=1;d<=dim;d++){
      var di=y+'-'+pad(m+1)+'-'+pad(d);
      var wd=(lead+d-1)%7;
      var cls=[];
      if(wd>=5)cls.push('weekend');
      var mk=marks[di];
      if(mk&&mk.o)cls.push('holiday');
      else if(mk)cls.push('special');
      frag.appendChild(span(cls.join(' '),String(d),di,mk?mk.n:null));
    }
    var tail=(lead+dim)%7;
    if(tail)for(var b=tail;b<7;b++)frag.appendChild(span('empty',''));
    grid.appendChild(frag);
    // "Helligdage denne maaned"-listen
    var official=[];
    for(var key in marks){
      if(marks[key].o&&key.slice(0,7)===iso.slice(0,7))official.push({d:key,n:marks[key].n});
    }
    official.sort(function(x,z){return x.d<z.d?-1:1;});
    var box=panel.querySelector('.quick-panel__holidays');
    var noh=panel.querySelector('.quick-panel__nohol');
    if(official.length){
      var div=document.createElement('div');
      div.className='quick-panel__holidays';
      var lis='';
      for(var e2=0;e2<official.length;e2++){
        lis+='<li><strong>'+official[e2].d.slice(8,10)+'/'+official[e2].d.slice(5,7)+'</strong> <span></span></li>';
      }
      div.innerHTML='<h3>Helligdage denne m\u00e5ned</h3><ul>'+lis+'</ul>';
      var its=div.querySelectorAll('li span');
      for(var f=0;f<its.length;f++)its[f].textContent=official[f].n;
      if(box)box.replaceWith(div);else if(noh)noh.replaceWith(div);else panel.appendChild(div);
    }else{
      var p=document.createElement('p');
      p.className='quick-panel__nohol muted';
      p.textContent='Ingen helligdage i denne m\u00e5ned.';
      if(box)box.replaceWith(p);else if(!noh)panel.appendChild(p);
    }
  }
  try{rebuildMiniCalendar();}catch(err){/* behold oprindeligt HTML */}

  var nodes=document.querySelectorAll('[data-date]');
  for(var i=0;i<nodes.length;i++){
    var el=nodes[i];
    if(el.getAttribute('data-date')===iso){
      el.classList.add('today');
    }
  }
  // Hamburger menu toggle (mobile)
  var btn=document.querySelector('.nav-toggle');
  var nav=document.getElementById('main-nav');
  if(btn && nav){
    btn.addEventListener('click',function(){
      var open=nav.classList.toggle('is-open');
      btn.setAttribute('aria-expanded',open?'true':'false');
      btn.setAttribute('aria-label',open?'Luk menu':'Åbn menu');
    });
  }
})();
