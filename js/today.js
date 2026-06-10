(function(){
  function pad(n){return n<10?'0'+n:''+n;}
  var now=new Date();
  var iso=now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate());
  var nodes=document.querySelectorAll('[data-date]');
  for(var i=0;i<nodes.length;i++){
    var el=nodes[i];
    if(el.getAttribute('data-date')===iso){
      el.classList.add('today');
    }
  }
})();
